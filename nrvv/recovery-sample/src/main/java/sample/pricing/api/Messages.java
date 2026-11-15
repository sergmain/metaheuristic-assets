package sample.pricing.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

/** The messages that travel over a {@link PriceChannel}. */
public final class Messages {

    private Messages() {
    }

    /** The highest price per litre a station may display. */
    public static final BigDecimal MAX_PRICE = new BigDecimal("9.999");

    /**
     * A new price for one station. {@code sequence} grows by one for every update the pricing office sends to the station,
     * so a station can tell a newer price from an older one whatever order the updates arrive in.
     *
     * @param stationId the station the price is for
     * @param sequence  1 for the station's first update, then one more for each later update
     * @param price     the price per litre, at most three decimal places, greater than zero and at most {@link #MAX_PRICE}
     * @param issuedAt  when the pricing office set the price
     */
    public record PriceUpdate(String stationId, long sequence, BigDecimal price, Instant issuedAt) {
        public PriceUpdate {
            if (stationId == null || stationId.isBlank()) {
                throw new IllegalArgumentException("a price update names its station");
            }
            if (sequence < 1) {
                throw new IllegalArgumentException("a station's first price update has sequence 1, got " + sequence);
            }
            Objects.requireNonNull(price, "price");
            Objects.requireNonNull(issuedAt, "issuedAt");
            if (price.signum() <= 0 || price.compareTo(MAX_PRICE) > 0) {
                throw new IllegalArgumentException("a price is greater than zero and at most " + MAX_PRICE + ", got " + price);
            }
            if (price.stripTrailingZeros().scale() > 3) {
                throw new IllegalArgumentException("a price has at most three decimal places, got " + price);
            }
        }
    }

    /**
     * A station's acknowledgement: it handled every update addressed to it up to and including {@code sequence} - applied
     * it, or dropped it as older than the price it displays.
     */
    public record Ack(String stationId, long sequence) {
        public Ack {
            if (stationId == null || stationId.isBlank()) {
                throw new IllegalArgumentException("an acknowledgement names its station");
            }
            if (sequence < 1) {
                throw new IllegalArgumentException("an acknowledgement names a sequence of 1 or more, got " + sequence);
            }
        }
    }
}
