package synthetic.corpus;

/**
 * SYNTHETIC development fixture for mh-rg-requirements-from-batch-internal-1.0 - not real code of any product.
 *
 * A token-bucket rate limiter. The bucket holds at most {@code capacity} tokens and starts full. Every call to
 * {@link #tryAcquire()} takes one token if one is available. Tokens come back at {@code refillPerSecond}, never above
 * the capacity.
 */
public class SyntheticRateLimiter {

    private final int capacity;
    private final double refillPerSecond;
    private double tokens;
    private long lastRefillNanos;

    public SyntheticRateLimiter(int capacity, double refillPerSecond, long nowNanos) {
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity must be at least 1, got " + capacity);
        }
        if (!(refillPerSecond > 0)) {
            throw new IllegalArgumentException("refillPerSecond must be positive, got " + refillPerSecond);
        }
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.tokens = capacity;
        this.lastRefillNanos = nowNanos;
    }

    /** Takes one token and answers true, or answers false and takes nothing when the bucket is empty. */
    public synchronized boolean tryAcquire(long nowNanos) {
        refill(nowNanos);
        if (tokens < 1) {
            return false;
        }
        tokens -= 1;
        return true;
    }

    private void refill(long nowNanos) {
        if (nowNanos <= lastRefillNanos) {
            return;
        }
        final double elapsedSeconds = (nowNanos - lastRefillNanos) / 1_000_000_000.0;
        tokens = Math.min(capacity, tokens + elapsedSeconds * refillPerSecond);
        lastRefillNanos = nowNanos;
    }
}
