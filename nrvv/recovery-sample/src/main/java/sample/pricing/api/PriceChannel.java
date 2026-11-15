package sample.pricing.api;

import java.util.Optional;

/**
 * The channel between the pricing office and the stations - the only way a price reaches a station.
 *
 * <p>A provider publishes price updates; a station's consumer polls the updates addressed to it and acknowledges each one
 * it has handled. An update stays pending for its station until that station acknowledges it.
 */
public interface PriceChannel {

    /** Publishes {@code update} to its station; it stays pending until the station acknowledges its sequence. */
    void publish(Messages.PriceUpdate update);

    /** The oldest pending update of {@code stationId}, or empty when the station has nothing pending. */
    Optional<Messages.PriceUpdate> poll(String stationId);

    /** The station's acknowledgement: every pending update of the station up to {@code ack.sequence()} is handled. */
    void acknowledge(Messages.Ack ack);
}
