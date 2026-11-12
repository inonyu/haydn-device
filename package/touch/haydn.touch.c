/*
 * The touch screen of haydn: FocalTech on SPI11. See haydn.touch.h for the
 * 15-bit report layout and docs/hardware.md for where the bus and pins came
 * from.
 *
 * The protocol code began as HakiOS's (drivers/input/hakios.goodix.c, the
 * FocalTech section) with this board's bus substituted. The report decode
 * here is the part that changed: HakiOS's own comment block documents the
 * 15-bit field packing, its focaltech_report() implements it, and an earlier
 * draft of this file read the same bytes as 12-bit values and was wrong.
 * tests/touch-format.py is the test that catches that class of mistake.
 *
 * What is NOT here: the SPI transfer itself. XNU has no generic SPI client
 * layer, and the GENI SPI controller needs the QcomGeniSpi component's
 * descriptor API rather than a register poke, so the one function that talks
 * to the controller is declared and left for whatever binds this driver.
 *
 * Boot argument: touchscreen=1
 */

#include <pexpert/pexpert.h>
#include <kern/printf.h>
#include <sys/time.h>

#include "haydn.touch.h"

/*
 * Supplied by whatever binds this driver to the GENI controller: a full
 * duplex transfer at HAYDN_TOUCH_SPI_HZ in mode 0. Returns TRUE on success.
 */
extern boolean_t haydn_touch_spi_transfer(const uint8_t *tx, uint8_t *rx, uint32_t length);

static uint8_t fts_tx[FTS_MAX_TRANSFER];
static uint8_t fts_rx[FTS_MAX_TRANSFER];

/*
 * CRC-16 with polynomial 0x8408 reflected and **initial value 0xffff**.
 *
 * Note the name: with init 0xffff this is CRC-16/MCRF4XX, not CRC-16/KERMIT
 * (which starts at 0x0000). HakiOS's comment calls it Kermit while using
 * 0xffff, and its remark "same as vendor rckit_crc16()" is the authority that
 * 0xffff is the right starting value for this family of parts. The vector
 * "123456789" produces 0x6f91 here; that is the test in tests/touch-format.py.
 */
static uint16_t
fts_crc(const uint8_t *data, uint32_t length)
{
	uint16_t crc = 0xffff;
	uint32_t i;
	int bit;

	for (i = 0; i < length; i++) {
		crc ^= data[i];
		for (bit = 0; bit < 8; bit++) {
			crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0x8408) : (uint16_t)(crc >> 1);
		}
	}
	return crc;
}

static boolean_t
fts_read(uint8_t address, uint8_t *data, uint32_t length)
{
	const uint32_t data_offset = FTS_SPI_HEADER_LENGTH;
	uint32_t transfer_length = data_offset + length + 2;
	int attempt;

	if (length == 0 || transfer_length > sizeof(fts_tx)) {
		return FALSE;
	}

	for (attempt = 0; attempt < 3; attempt++) {
		uint16_t expected, received;
		uint32_t i;

		for (i = 0; i < transfer_length; i++) {
			fts_tx[i] = 0;
			fts_rx[i] = 0;
		}
		fts_tx[0] = address;
		fts_tx[1] = FTS_READ_CTRL;
		fts_tx[2] = (uint8_t)(length >> 8);
		fts_tx[3] = (uint8_t)(length & 0xff);

		if (!haydn_touch_spi_transfer(fts_tx, fts_rx, transfer_length)) {
			delay_for_us(150);
			continue;
		}
		/* Bit 7 of the status byte is BUSY, bit 5 is a CRC error. */
		if (fts_rx[3] & 0xa0) {
			delay_for_us(150);
			continue;
		}

		expected = fts_crc(fts_rx + data_offset, length);
		received = (uint16_t)(fts_rx[data_offset + length] |
		    (uint16_t)fts_rx[data_offset + length + 1] << 8);
		if (expected != received) {
			delay_for_us(150);
			continue;
		}

		for (i = 0; i < length; i++) {
			data[i] = fts_rx[data_offset + i];
		}
		/* The vendor's minimum chip-select high time. */
		delay_for_us(150);
		return TRUE;
	}
	return FALSE;
}

int
haydn_touch_probe(struct haydn_touch_info *out)
{
	uint32_t enabled = 0;
	uint8_t high = 0, low = 0;
	int attempt;

	if (!PE_parse_boot_argn("touchscreen", &enabled, sizeof(enabled)) || !enabled) {
		return 1;
	}

	/* The vendor polls for up to a second in 200 ms steps before giving up. */
	for (attempt = 0; attempt < 5; attempt++) {
		if (fts_read(FTS_CHIP_ID_H, &high, 1) &&
		    fts_read(FTS_CHIP_ID_L, &low, 1)) {
			printf("haydn-touch: chip id %02x %02x on attempt %d\n",
			    high, low, attempt + 1);
			break;
		}
		delay_for_us(200000);
	}

	if (attempt == 5) {
		printf("haydn-touch: no answer on SPI at %d Hz - check GPIO 22/23 and the rail\n",
		    HAYDN_TOUCH_SPI_HZ);
		return 2;
	}

	out->chip_id_high = high;
	out->chip_id_low = low;
	out->points = HAYDN_TOUCH_MAX_POINTS;

	printf("haydn-touch: %d points, report space %dx%d normalised to 0..65535\n",
	    out->points, HAYDN_TOUCH_REPORT_X, HAYDN_TOUCH_REPORT_Y);

	return 0;
}

/*
 * The decode. Pure: a function of the bytes alone, so the test can drive it
 * with constructed reports and know that a wrong answer is the format's fault
 * and not the bus's.
 */
int
haydn_touch_decode(const uint8_t *report, size_t length,
    struct haydn_touch_event *events, int max_events)
{
	int count = 0;
	int slot;

	if (report == NULL || events == NULL || max_events <= 0) {
		return 0;
	}
	if (length < (size_t)FTS_TOUCH_REPORT_LEN) {
		return 0;
	}

	for (slot = 0; slot < FTS_MAX_TOUCHES && count < max_events; slot++) {
		const uint8_t *t = report + 2 + 6 * slot;
		uint8_t id = (uint8_t)((t[2] >> 4) & 0x0f);
		uint8_t event = (uint8_t)((t[0] >> 6) & 0x3);
		uint32_t x, y;

		/* An id beyond the panel's slots ends the report. */
		if (id >= FTS_MAX_TOUCHES) {
			break;
		}

		/* 15 bits, packed the way the header comment describes. */
		x = ((uint32_t)(t[0] & 0x0f) << 11) |
		    ((uint32_t)t[1] << 3) |
		    ((uint32_t)t[4] >> 5);
		y = ((uint32_t)(t[2] & 0x0f) << 11) |
		    ((uint32_t)t[3] << 3) |
		    (((uint32_t)t[4] & 0x1c) >> 2);

		/*
		 * The chip can report past the panel's extent; clamp before scaling so
		 * the multiply below cannot overflow a 16-bit result.
		 */
		if (x > HAYDN_TOUCH_REPORT_X - 1) {
			x = HAYDN_TOUCH_REPORT_X - 1;
		}
		if (y > HAYDN_TOUCH_REPORT_Y - 1) {
			y = HAYDN_TOUCH_REPORT_Y - 1;
		}

		events[count].x = (uint16_t)(((uint64_t)x * 65535) / (HAYDN_TOUCH_REPORT_X - 1));
		events[count].y = (uint16_t)(((uint64_t)y * 65535) / (HAYDN_TOUCH_REPORT_Y - 1));
		events[count].id = id;
		events[count].event = event;
		count++;
	}

	return count;
}

int
haydn_touch_poll(struct haydn_touch_event *events, int max_events)
{
	static uint8_t report[FTS_TOUCH_REPORT_LEN];

	if (!fts_read(FTS_TOUCH_DATA, report, sizeof(report))) {
		return 0;
	}

	/* The vendor treats an all-ones header as "not a report". */
	if (report[1] == 0xff && report[2] == 0xff && report[3] == 0xff) {
		return 0;
	}

	return haydn_touch_decode(report, sizeof(report), events, max_events);
}
