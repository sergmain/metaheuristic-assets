package sample.pricing.provider;

import sample.pricing.api.Messages;
import sample.pricing.api.PriceChannel;

import java.math.BigDecimal;
import java.time.Clock;
import java.util.HashMap;
import java.util.Map;

/**
 * The pricing office's side of the channel: it turns each price the office sets into an update for the station, numbered
 * in the order the office set the station's prices.
 */
public class Provider {

    private final PriceChannel channel;
    private final Clock clock;
    private final Map<String, Long> lastSequence = new HashMap<>();
    private final Map<String, BigDecimal> lastPrice = new HashMap<>();

    public Provider(PriceChannel channel, Clock clock) {
        this.channel = channel;
        this.clock = clock;
    }

    /**
     * Sets {@code price} for {@code stationId} and publishes it. A price equal to the station's last published price is not
     * sent again - every send has a cost - and false is returned.
     */
    public synchronized boolean setPrice(String stationId, BigDecimal price) {
        final BigDecimal last = lastPrice.get(stationId);
        if (last != null && last.compareTo(price) == 0) {
            return false;
        }
        final long sequence = lastSequence.getOrDefault(stationId, 0L) + 1;
        final Messages.PriceUpdate update = new Messages.PriceUpdate(stationId, sequence, price, clock.instant());
        channel.publish(update);
        lastSequence.put(stationId, sequence);
        lastPrice.put(stationId, price);
        return true;
    }

    /** The sequence of the last update published to {@code stationId}; 0 when none was. */
    public synchronized long lastSequence(String stationId) {
        return lastSequence.getOrDefault(stationId, 0L);
    }
}
