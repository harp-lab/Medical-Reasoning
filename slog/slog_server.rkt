#lang racket

;; Long-lived Slog session server.
;;
;; Owns one slogd with the KG2 database resident, and answers JSON-line requests
;; over TCP on 127.0.0.1.  It is a separate process from the MCP server on
;; purpose: restarting Claude Code must not cost a 5-minute reload.
;;
;; Protocol -- one JSON object per request, one per response:
;;   {"op":"status"}                        -> {ok, loaded, db, load_s, uptime_s, slogd_pid}
;;   {"op":"schema"}                        -> {ok, relations:[...]}     (loads if cold)
;;   {"op":"run","program":"<slog text>"}   -> {ok, elapsed_s}
;;   {"op":"dump","rel":"foo","limit":500}  -> {ok, n_rows, returned, truncated, rows}
;;   {"op":"drop","rel":"foo"}              -> {ok}
;; Errors are {"ok":false,"error":"..."} and never close the connection.
;;
;; Launch through kg2-server.sh, which supplies the clang toolchain env and the
;; memory cap.

(require racket/tcp
         json
         (file "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog/compiler/session.rkt"))

(define SLOG-ROOT "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog")
(define MR-ROOT "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/MedicalReasoning")
(define SETUP (build-path MR-ROOT "slog" "setup.slog"))
(define DB (or (getenv "KG2_SLOG_DB") "dataTest3"))
(define PORT (string->number (or (getenv "SLOG_SERVER_PORT") "8642")))

;; slog resolves daemon/ build/ out/ data/ against the cwd, so the process has to
;; sit in the slog repo regardless of where it was launched from.
(current-directory SLOG-ROOT)

(define (note fmt . args)
  (eprintf "[slog-server] ~a\n" (apply format fmt args))
  (flush-output (current-error-port)))

;; ---- session state --------------------------------------------------------
;; One daemon, so every request serializes on this lock.
(define lock (make-semaphore 1))
(define sess #f)
(define load-seconds 0.0)
(define started (current-inexact-monotonic-milliseconds))
;; An out-of-memory pause leaves the session in an unverified state; once we see
;; one, say so rather than pretending later answers are trustworthy.
(define suspect #f)

(define recent '())
(define (remember line)
  (set! recent (cons line (if (> (length recent) 30) (take recent 30) recent))))

(define (ensure-session!)
  (unless sess
    (note "opening ~a (expect several minutes and tens of GB)" DB)
    (define t0 (current-inexact-monotonic-milliseconds))
    (define s (make-session #:echo remember))
    (session-open! s DB)
    (note "database open; defining views from setup.slog")
    (session-run! s (path->string SETUP))
    (set! load-seconds (/ (- (current-inexact-monotonic-milliseconds) t0) 1000.0))
    (set! sess s)
    (note "READY in ~as" (real->decimal-string load-seconds 1)))
  sess)

;; ---- daemon line readers --------------------------------------------------
(define (collect-until out sentinel-px keep-px)
  (let loop ([acc '()])
    (define line (read-line out))
    (cond
      [(eof-object? line) (values (reverse acc) #f)]
      [(regexp-match sentinel-px line) => (lambda (m) (values (reverse acc) line))]
      [(regexp-match? keep-px line) (loop (cons line acc))]
      [else (loop acc)])))

(define (schema-lines s)
  (define out-lines '())
  (session-action! s '(schema)
    (lambda (out)
      (define-values (ls _end) (collect-until out #px"^\\(schema-end" #px"^\\(schema-rel"))
      (set! out-lines ls)))
  out-lines)

;; (dump-tuples r) emits one (tuplerow v0 v1 ...) per row then (tupledone N).
;; dump-rel is column-0 only (it exists for the driver's error watch), so this
;; is the action that returns whole tuples.
(define (dump-tuples s rel limit)
  (define rows '())
  (define kept 0)
  (define total 0)
  (session-action! s `(dump-tuples ,(string->symbol rel))
    (lambda (out)
      (let loop ()
        (define line (read-line out))
        (cond
          [(eof-object? line) (void)]
          [(regexp-match #px"^\\(tupledone ([0-9]+)\\)" line)
           => (lambda (m) (set! total (string->number (cadr m))))]
          [(regexp-match? #px"^\\(tuplerow" line)
           ;; the row is a readable s-expression; let the reader handle quoting
           (when (< kept limit)
             (define parsed
               (with-handlers ([exn:fail? (lambda (_) #f)])
                 (read (open-input-string line))))
             (set! rows (cons (if (and (list? parsed) (pair? parsed))
                                  (for/list ([v (cdr parsed)])
                                    (if (string? v) v (format "~a" v)))
                                  (list line))
                              rows))
             (set! kept (add1 kept)))
           (loop)]
          [else (loop)]))))
  (values (reverse rows) total))

;; ---- request dispatch ----------------------------------------------------
(define (slogd-pid)
  (with-handlers ([exn:fail? (lambda (_) 'null)])
    (define s (with-output-to-string (lambda () (system "pgrep -u $USER -n slogd"))))
    (define n (string->number (string-trim s)))
    (or n 'null)))

(define (handle req)
  (define op (hash-ref req 'op "?"))
  (case op
    [("status")
     (hasheq 'ok #t 'loaded (and sess #t) 'db DB
             'load_s (/ (round (* 10 load-seconds)) 10.0)
             'uptime_s (/ (round (- (current-inexact-monotonic-milliseconds) started)) 1000.0)
             'suspect suspect
             'slogd_pid (if sess (slogd-pid) 'null))]
    [("schema")
     (define s (ensure-session!))
     (hasheq 'ok #t 'relations (schema-lines s))]
    [("run")
     (define s (ensure-session!))
     (define program (hash-ref req 'program #f))
     (unless program (error 'run "no program given"))
     (define tmp (make-temporary-file "slogq~a.slog"))
     (call-with-output-file tmp #:exists 'truncate
       (lambda (o) (display program o)))
     (define t0 (current-inexact-monotonic-milliseconds))
     (begin0
       (with-handlers ([exn:fail?
                        (lambda (e)
                          (when (regexp-match? #px"out of memory" (exn-message e))
                            (set! suspect #t))
                          (raise e))])
         (session-run! s (path->string tmp))
         (hasheq 'ok #t 'elapsed_s
                 (/ (round (- (current-inexact-monotonic-milliseconds) t0)) 1000.0)))
       (with-handlers ([exn:fail? void]) (delete-file tmp)))]
    [("dump")
     (define s (ensure-session!))
     (define rel (hash-ref req 'rel #f))
     (unless rel (error 'dump "no rel given"))
     (define limit (hash-ref req 'limit 500))
     (define-values (rows total) (dump-tuples s rel limit))
     (hasheq 'ok #t 'n_rows total 'returned (length rows)
             'truncated (> total (length rows)) 'rows rows)]
    [("drop")
     (define s (ensure-session!))
     (session-drop! s (hash-ref req 'rel))
     (hasheq 'ok #t)]
    [else (error 'handle "unknown op: ~a" op)]))

(define (serve in out)
  (let loop ()
    (define req (with-handlers ([exn:fail? (lambda (_) eof)]) (read-json in)))
    (unless (eof-object? req)
      (define resp
        (with-handlers ([exn:fail?
                         (lambda (e)
                           (note "error: ~a" (exn-message e))
                           (hasheq 'ok #f 'error (exn-message e)))])
          (call-with-semaphore lock (lambda () (handle req)))))
      (write-json resp out)
      (newline out)
      (flush-output out)
      (loop))))

(note "listening on 127.0.0.1:~a (db ~a, cold until first request)" PORT DB)
(define listener (tcp-listen PORT 8 #t "127.0.0.1"))
(let accept-loop ()
  (define-values (in out) (tcp-accept listener))
  (thread (lambda ()
            (with-handlers ([exn:fail? (lambda (e) (note "connection: ~a" (exn-message e)))])
              (serve in out))
            (close-input-port in)
            (close-output-port out)))
  (accept-loop))
