#lang racket

(require racket/tcp
         json
         (file "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/slog/compiler/session.rkt"))

(define SLOG-ROOT "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/slog")
(define MR-ROOT "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/projects/MedicalReasoning")
(define SETUP (build-path MR-ROOT "slog" "setup.slog"))
(define DB (or (getenv "KG2_SLOG_DB") "rtx_kg2_281"))
(define PORT (string->number (or (getenv "SLOG_SERVER_PORT") "8642")))

(current-directory SLOG-ROOT)

(define (note fmt . args)
  (eprintf "[slog-server] ~a\n" (apply format fmt args))
  (flush-output (current-error-port)))

(define lock (make-semaphore 1))
(define sess #f)

(define (ensure-session!)
  (unless sess
    (note "opening ~a" DB)
    (define t0 (current-inexact-monotonic-milliseconds))
    (define s (make-session #:echo void))
    (session-open! s DB)
    (note "defining views from setup.slog")
    (session-run! s (path->string SETUP))
    (set! sess s)
    (note "READY in ~as"
          (real->decimal-string
           (/ (- (current-inexact-monotonic-milliseconds) t0) 1000.0) 1)))
  sess)

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

(define (handle req)
  (define op (hash-ref req 'op "?"))
  (case op
    [("run")
     (define s (ensure-session!))
     (define path (hash-ref req 'path #f))
     (unless path (error 'run "no path given"))
     (unless (file-exists? path) (error 'run "no such file: ~a" path))
     (session-run! s path)
     (hasheq 'ok #t)]
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

(note "loading ~a before accepting connections" DB)
(void (ensure-session!))

(note "listening on 127.0.0.1:~a (db ~a, ready)" PORT DB)
(define listener (tcp-listen PORT 8 #t "127.0.0.1"))
(let accept-loop ()
  (define-values (in out) (tcp-accept listener))
  (thread (lambda ()
            (with-handlers ([exn:fail? (lambda (e) (note "connection: ~a" (exn-message e)))])
              (serve in out))
            (close-input-port in)
            (close-output-port out)))
  (accept-loop))
