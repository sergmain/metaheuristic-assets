package sample.pricing.consumer;

import sample.pricing.api.Messages;
import sample.pricing.api.PriceChannel;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.util.Optional;

/**
 * A station's side of the channel: it displays the newest price the pricing office set for the station, whatever order
 * the updates arrive in, and acknowledges every update it handled.
 */
public class Consumer {

    /** An update issued longer ago than this is not displayed - the station keeps its price - but it is acknowledged. */
    public static final Duration MAX_AGE = Duration.ofMinutes(15);

    private final String stationId;
    private final PriceChannel channel;
    private final Clock clock;
    private long appliedSequence;
    private BigDecimal displayed;

    public Consumer(String stationId, PriceChannel channel, Clock clock) {
        this.stationId = stationId;
        this.channel = channel;
        this.clock = clock;
    }

    /**
     * Handles the station's oldest pending update, if any: an update newer than the displayed price and not older than
     * {@link #MAX_AGE} is displayed; an older or a stale one is dropped. Either way it is acknowledged, so the channel
     * never offers it again. Returns whether an update was handled.
     */
    public synchronized boolean handleNext() {
        final Optional<Messages.PriceUpdate> next = channel.poll(stationId);
        if (next.isEmpty()) {
            return false;
        }
        final Messages.PriceUpdate update = next.get();
        final boolean newer = update.sequence() > appliedSequence;
        final boolean fresh = !update.issuedAt().plus(MAX_AGE).isBefore(clock.instant());
        if (newer && fresh) {
            displayed = update.price();
            appliedSequence = update.sequence();
        }
        channel.acknowledge(new Messages.Ack(stationId, update.sequence()));
        return true;
    }

    /** The price the station displays; empty until the first update is applied. */
    public synchronized Optional<BigDecimal> displayed() {
        return Optional.ofNullable(displayed);
    }

    /** The sequence of the displayed price; 0 until the first update is applied. */
    public synchronized long appliedSequence() {
        return appliedSequence;
    }
}
