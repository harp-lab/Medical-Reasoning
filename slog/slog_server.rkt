#lang racket

;; Paths are derived from this file's own location, not spelled absolutely: the
;; tree moved once already (both checkouts now live under MR/) and every
;; hardcoded path broke at once.  The only assumption left is that the slog and
;; MedicalReasoning checkouts stay SIBLINGS.
;;
;; A plain-string require resolves relative to THIS module's directory, so it
;; survives the move for free; `(file "...")` would not.
(require racket/tcp
         racket/runtime-path
         json
         "../../slog/compiler/session.rkt")

(define-runtime-path HERE ".")                       ; MedicalReasoning/slog/
(define MR-ROOT (simplify-path (build-path HERE 'up)))
(define SLOG-ROOT
  (or (getenv "SLOG_ROOT")
      (path->string (simplify-path (build-path MR-ROOT 'up "slog")))))
(define SETUP (build-path HERE "setup.slog"))
(define DB (or (getenv "KG2_SLOG_DB") "rtx_kg2_281"))
(define PORT (string->number (or (getenv "SLOG_SERVER_PORT") "8642")))

;; slog resolves build/, data/ and the plan cache relative to the cwd.
(unless (directory-exists? SLOG-ROOT)
  (error 'slog-server
         (string-append "no slog checkout at ~a -- expected it beside "
                        "MedicalReasoning/, or set SLOG_ROOT")
         SLOG-ROOT))
(current-directory SLOG-ROOT)

(define (note fmt . args)
  (eprintf "[slog-server] ~a\n" (apply format fmt args))
  (flush-output (current-error-port)))

(define lock (make-semaphore 1))
(define sess #f)

;; The session driver echoes every line the daemon emits while a stratum runs
;; -- including the two we care about for join-plan provenance:
;;
;;   (fixpoint SCC "HASH" ITERS MS)   HASH names build/HASH.plan, the compiled
;;                                    join order this stratum actually ran
;;   (arms (g GID ARM CONVERGED "LOC") ...)
;;                                    which arm of each SLOG_MULTIPLAN choice
;;                                    group the daemon's runtime selection picked
;;
;; make-session's default echo is displayln and this server used `void` (silent,
;; dropped).  Collect instead, and hand the lines back on the `run` reply so the
;; Python side can resolve the plans.  Capped so a pathological run (many
;; memory pauses, many strata) cannot grow the reply without bound.
(define EVENT-CAP 5000)
;; The lines above are kept whole; everything else is trimmed to a stub.  A
;; `(pipeline ...)` line alone is several KB of version-ids -- diagnostic in
;; principle, but it would dominate every reply, so keep its head and drop the
;; body rather than dropping the line and pretending nothing was said.
(define KEEP-WHOLE #px"^\\((fixpoint|arms|tier|paused|refused|error|recount|activated) ")
(define STUB-AT 160)
(define events (box '()))
(define event-count (box 0))
;; Each line is stamped with milliseconds since the run began.  The daemon does
;; substantial work BETWEEN these lines -- the whole-DB reload that
;; `reloadInsertBatches` arms after every fixpoint re-stages every relation as
;; delta and clears every index, and the next stratum re-interns it -- and none
;; of that shows up in `(fixpoint ...)`'s own ms.  Without the stamps a run that
;; spends 30s in the fixpoint and 136s around it looks identical to one that
;; spends 166s joining.
(define run-t0 (box (current-inexact-monotonic-milliseconds)))
(define (elapsed-ms)
  (inexact->exact
   (round (- (current-inexact-monotonic-milliseconds) (unbox run-t0)))))
;; The reply is capped and stubbed because it crosses a socket and lands in a
;; model's context.  A `tee` path on the run request asks for the OTHER copy:
;; every echoed line, whole, uncapped, written as it arrives.  The stamp stays
;; -- it is the only record of WHEN a line appeared, and the gaps between lines
;; are where this KG's wall time actually goes -- but it is split off by a tab,
;; so everything past the first tab is the line exactly as it was echoed.
;;
;; Written incrementally rather than at the end: a run is minutes long and gets
;; interrupted, and a partial stream of a run that died is worth more than
;; nothing at all.
(define tee-port (box #f))
(define (tee! at line)
  (define p (unbox tee-port))
  (when p
    (with-handlers ([exn:fail?
                     (lambda (e)
                       (note "tee write failed, dropping it: ~a" (exn-message e))
                       (set-box! tee-port #f))])
      (fprintf p "+~a\t~a\n" at line)
      (flush-output p))))

(define (note-event! line)
  (define at (elapsed-ms))
  (tee! at line)
  (when (< (unbox event-count) EVENT-CAP)
    (define kept
      (cond
        [(regexp-match? KEEP-WHOLE line) line]
        [(<= (string-length line) STUB-AT) line]
        [else (string-append (substring line 0 STUB-AT) " ...)")]))
    (set-box! events (cons (format "+~a ~a" at kept) (unbox events))))
  (set-box! event-count (add1 (unbox event-count))))
(define (take-events!)
  (define out (reverse (unbox events)))
  (define n (unbox event-count))
  (set-box! events '())
  (set-box! event-count 0)
  (if (> n EVENT-CAP)
      (append out (list (format "(events-truncated ~a ~a)" EVENT-CAP n)))
      out))

(define (ensure-session!)
  (unless sess
    (note "opening ~a" DB)
    (define t0 (current-inexact-monotonic-milliseconds))
    (define s (make-session #:echo note-event!))
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
     ;; Drop anything queued by session startup / a previous op so `events`
     ;; describes THIS run only, and zero the clock the stamps count from.
     (void (take-events!))
     (set-box! run-t0 (current-inexact-monotonic-milliseconds))
     ;; A tee that cannot be opened is reported and skipped, never fatal: the
     ;; run is the expensive thing and it should not die over a log file.
     (define tee-path (hash-ref req 'tee #f))
     (define tee-out
       (and tee-path
            (with-handlers ([exn:fail?
                             (lambda (e)
                               (note "cannot open tee ~a: ~a" tee-path (exn-message e))
                               #f)])
              (open-output-file tee-path #:exists 'truncate))))
     (set-box! tee-port tee-out)
     (dynamic-wind
       void
       (lambda ()
         (session-run! s path)
         (note-event! "(run-complete)"))
       (lambda ()
         (set-box! tee-port #f)
         (when tee-out (close-output-port tee-out))))
     ;; `tiers` is (scc hash rung cached-rungs policy) per resident stratum --
     ;; the authoritative stratum-hash -> build/HASH.plan mapping, including
     ;; strata that were cached and so emitted no fixpoint line this run.
     (hasheq 'ok #t
             ;; Whether the untruncated copy actually landed.  A client that
             ;; asked for one and got #f back knows to fall back to `events`
             ;; rather than reading a file that is not there.
             'tee (and tee-out tee-path)
             'events (take-events!)
             'tiers (for/list ([t (in-list (session-tiers s))])
                      (hasheq 'scc (first t)
                              'hash (format "~a" (second t))
                              'rung (format "~a" (third t))
                              'cached (for/list ([r (in-list (fourth t))])
                                        (format "~a" r))))
             ;; The planner knobs as THIS process has them.  The MCP server is a
             ;; separate process that never sees kg2-server.sh's environment, so
             ;; without this it cannot tell an empty arm set ("multiplan off")
             ;; from a real one ("on, but nothing was eligible").
             'env (hasheq 'multiplan (or (getenv "SLOG_MULTIPLAN") "")
                          'multiplan_index (or (getenv "SLOG_MULTIPLAN_INDEX") "")
                          'opt (or (getenv "SLOG_OPT") "")))]
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
