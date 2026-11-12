/*
 * The touch screen of haydn: a FocalTech controller on the SoC's SPI11, as
 * a source of touches in a normalised 0..65535 space.
 *
 * From the phone's own device tree (spi@a8c000/focaltech@0):
 *
 *   compatible        focaltech,fts
 *   spi-max-frequency 0x5b8d80 = 6,000,000 Hz
 *   reset-gpio        <&tlmm 0x16 0x00>  = GPIO 22
 *   irq-gpio          <&tlmm 0x17 0x2008> = GPIO 23, falling edge
 *   max-touch-number  10
 *   display-coords    0,0 -> 0x21c0,0x4b00 (8640 x 19200)
 *
 * and from the live phone: focaltech_touch.ko is loaded and
 * /sys/bus/spi/devices/spi1.0 is bound to fts_ts.
 *
 * --- The report format, and why the first version was wrong -------------------
 *
 * The coordinates are **15-bit** values split across four and a bit bytes, not
 * the 12-bit layout a naive reading of the vendor offsets suggests:
 *
 *   report[0]             gesture (0 outside gesture mode)
 *   report[1]             (chip_type << 4) | finger_count
 *   report[2 + 6*i + 0]   E_XH:   bits 7..6 event, bits 3..0 x bits 14..11
 *   report[2 + 6*i + 1]   XL:     x bits 10..3
 *   report[2 + 6*i + 2]   ID_YH:  bits 7..4 finger id, bits 3..0 y bits 14..11
 *   report[2 + 6*i + 3]   YL:     y bits 10..3
 *   report[2 + 6*i + 4]   PRE:    bits 7..5 x bits 2..0, bits 4..2 y bits 2..0
 *   report[2 + 6*i + 5]   AREA:   touch area
 *
 * so:
 *
 *   x = ((t[0] & 0x0f) << 11) | (t[1] << 3) | (t[4] >> 5)
 *   y = ((t[2] & 0x0f) << 11) | (t[3] << 3) | ((t[4] & 0x1c) >> 2)
 *
 * 15 bits reach 32767, which is what makes the 8640 x 19200 report space
 * representable at all. A 12-bit reading tops out at 4095 and cannot express
 * either axis; an implementation built on it decodes every touch to the wrong
 * place, and does so silently. The round-trip test in
 * tests/touch-format.py is what caught it here.
 *
 * Events: 0 = down, 1 = up, 2 = contact (a moving finger).
 *
 * Boot argument: touchscreen=1
 */
#ifndef HAYDN_TOUCH_H
#define HAYDN_TOUCH_H

#include <sys/types.h>

/* From the device tree. */
#define HAYDN_TOUCH_SPI_HZ      6000000
#define HAYDN_TOUCH_RESET_GPIO  22
#define HAYDN_TOUCH_IRQ_GPIO    23
#define HAYDN_TOUCH_MAX_POINTS  10

/*
 * The chip's report space, from the device tree's focaltech,display-coords.
 * It is not the panel's pixel size: the panel is 1080 x 2400 and the chip
 * reports in an 8x finer space. Coordinates are normalised to 0..65535 before
 * they leave this driver, the way the platform's digitizer wants them.
 */
#define HAYDN_TOUCH_REPORT_X    8640
#define HAYDN_TOUCH_REPORT_Y    19200

/* The panel, for logging and for a board that wants pixels instead. */
#define HAYDN_PANEL_WIDTH       1080
#define HAYDN_PANEL_HEIGHT      2400

/* FTS 5.x framing. */
#define FTS_READ_CTRL           0xa0
#define FTS_WRITE_CTRL          0x00
#define FTS_SPI_HEADER_LENGTH   7
#define FTS_CHIP_ID_H           0xa3
#define FTS_CHIP_ID_L           0x9f
#define FTS_TOUCH_DATA          0x01
#define FTS_MAX_TOUCHES         10
#define FTS_TOUCH_REPORT_LEN    (2 + 6 * FTS_MAX_TOUCHES)
#define FTS_MAX_TRANSFER        (FTS_SPI_HEADER_LENGTH + FTS_TOUCH_REPORT_LEN + 2)

/* Event codes from E_XH bits 7..6. */
#define FTS_EVENT_DOWN          0
#define FTS_EVENT_UP            1
#define FTS_EVENT_CONTACT       2

/* One decoded point, in the platform's 0..65535 digitizer space. */
struct haydn_touch_event {
	uint16_t x;
	uint16_t y;
	uint8_t  id;
	uint8_t  event;
};

struct haydn_touch_info {
	uint8_t chip_id_high;
	uint8_t chip_id_low;
	int     points;
};

/* Read the chip's identity. Returns 0 when it answered. */
int haydn_touch_probe(struct haydn_touch_info *out);

/*
 * Decode one report into `events`. Returns the number written.
 *
 * Pure function of the bytes: no hardware, no globals that matter, so the
 * round-trip test can call it directly.
 */
int haydn_touch_decode(const uint8_t *report, size_t length,
    struct haydn_touch_event *events, int max_events);

/* Read one report from the chip and decode it. Returns the number written. */
int haydn_touch_poll(struct haydn_touch_event *events, int max_events);

#endif /* HAYDN_TOUCH_H */
