#lang racket

;; Load the KG2 slog database into a resident session and HOLD it.
;;
;; Two purposes:
;;   1. Answer "can we actually allocate ~80 GB and load the whole thing" --
;;      Linux has no way for an unprivileged user to reserve RAM in advance
;;      (no cgroup delegation, memlock capped at 8 MB), so the only real
;;      allocation is to take the pages and keep them.
;;   2. Prototype the backend the MCP server would use: one resident slogd,
;;      load once, then answer many queries.
;;
;; Prints READY once loaded.  Then reads commands on stdin, one per line:
;;   <path/to/query.slog>   run that program, print derived relation sizes
;;   sizes                  re-report the live schema
;;   quit                   close the session and exit
;;
;; Run it through kg2-hold.sh, which sets the toolchain env.

(require (file "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog/compiler/session.rkt"))

(define SLOG-ROOT "/home.na1/ad.wsu.edu/aayush.shrestha/pvt/Projects/slog")
(define DB (or (getenv "KG2_SLOG_DB") "dataTest3"))

;; slog resolves daemon/ build/ out/ data/ against the cwd, so the process has
;; to sit in the slog repo even though we were launched from elsewhere.
(current-directory SLOG-ROOT)

(define (note fmt . args) (eprintf "~a\n" (apply format fmt args)) (flush-output (current-error-port)))

;; make-session echoes every daemon line; keep the last few for diagnostics
;; rather than flooding stderr with plugin paths.
(define recent '())
(define (remember line)
  (set! recent (cons line (if (> (length recent) 40) (take recent 40) recent))))

;; (schema) reports one (schema-rel ...) per non-empty relation of the LIVE db
;; and terminates with (schema-end) -- a real sentinel, unlike (sizes).
(define (read-until-sentinel out sentinel-px)
  (let loop ([acc '()])
    (define line (read-line out))
    (cond
      [(eof-object? line) (reverse acc)]
      [(regexp-match? sentinel-px line) (reverse acc)]
      [else (loop (cons line acc))])))

(define (schema! s)
  (session-action! s '(schema)
    (lambda (out)
      (for ([l (read-until-sentinel out #px"^\\(schema-end")])
        (printf "~a\n" l))
      (flush-output))))

(define s (make-session #:echo remember))

(with-handlers ([exn:fail? (lambda (e)
                             (note "LOAD FAILED: ~a" (exn-message e))
                             (note "last daemon lines:")
                             (for ([l (reverse (take recent (min 10 (length recent))))]) (note "  ~a" l))
                             (exit 1))])
  (define t0 (current-inexact-monotonic-milliseconds))
  (note "opening database ~a ..." DB)
  (session-open! s DB)
  (define secs (/ (- (current-inexact-monotonic-milliseconds) t0) 1000.0))
  (note "loaded in ~as" (real->decimal-string secs 1)))

(printf "--- live schema ---\n")
(schema! s)
(printf "READY\n")
(flush-output)

;; Hold the memory and stay available for queries.
(let loop ()
  (define line (read-line))
  (cond
    [(or (eof-object? line) (string=? (string-trim line) "quit"))
     (note "closing session")
     (with-handlers ([exn:fail? void]) (session-close! s))]
    [(string=? (string-trim line) "") (loop)]
    [(string=? (string-trim line) "sizes") (schema! s) (printf "OK\n") (flush-output) (loop)]
    [else
     (with-handlers ([exn:fail? (lambda (e)
                                  (printf "ERROR ~a\n" (exn-message e))
                                  (flush-output))])
       (define t0 (current-inexact-monotonic-milliseconds))
       (session-run! s (string-trim line))
       (define secs (/ (- (current-inexact-monotonic-milliseconds) t0) 1000.0))
       (printf "RAN in ~as\n" (real->decimal-string secs 1))
       (schema! s)
       (printf "OK\n")
       (flush-output))
     (loop)]))
