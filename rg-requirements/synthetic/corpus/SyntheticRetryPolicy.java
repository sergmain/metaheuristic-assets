package synthetic.corpus;

import java.time.Duration;
import java.util.Set;

/**
 * SYNTHETIC development fixture for mh-rg-requirements-from-batch-internal-1.0 - not real code of any product.
 *
 * Decides whether a failed call is retried and how long to wait first. At most {@code maxAttempts} attempts are made
 * in total. The delay doubles with every attempt, starting at {@code initialDelay}, and never exceeds
 * {@code maxDelay}. An exception of a type listed as non-retryable is never retried.
 */
public class SyntheticRetryPolicy {

    private final int maxAttempts;
    private final Duration initialDelay;
    private final Duration maxDelay;
    private final Set<Class<? extends Throwable>> nonRetryable;

    public SyntheticRetryPolicy(int maxAttempts, Duration initialDelay, Duration maxDelay,
                                Set<Class<? extends Throwable>> nonRetryable) {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be at least 1, got " + maxAttempts);
        }
        if (initialDelay.isNegative() || maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException("delays must satisfy 0 <= initialDelay <= maxDelay");
        }
        this.maxAttempts = maxAttempts;
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
        this.nonRetryable = Set.copyOf(nonRetryable);
    }

    /** Whether the call that just failed with {@code error} on attempt {@code attempt} (1-based) is retried. */
    public boolean shouldRetry(int attempt, Throwable error) {
        if (attempt >= maxAttempts) {
            return false;
        }
        return nonRetryable.stream().noneMatch(t -> t.isInstance(error));
    }

    /** The wait before attempt {@code attempt + 1}: initialDelay * 2^(attempt-1), capped at maxDelay. */
    public Duration delayBefore(int nextAttempt) {
        final int exponent = Math.max(0, Math.min(nextAttempt - 2, 30));
        final Duration delay = initialDelay.multipliedBy(1L << exponent);
        return delay.compareTo(maxDelay) > 0 ? maxDelay : delay;
    }
}
