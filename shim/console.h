#pragma once
#include <stdint.h>

/* haydn: the ABL leaves the panel's splash buffer at 0xdfc00000 and reserves
 * 0x2300000 bytes there (cont_splash_region). sweet's 0x9c000000 is a different
 * board; painting it here would write over whatever lives at that address. */
#define FB_BASE		0xdfc00000UL	/* cont_splash_region, docs/hardware.md */
#define FB_W		1080
#define FB_H		2400
#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, matches mainline simplefb */

#define RED	0xffff0000U
#define BLUE	0xff0000a0U
#define WHITE	0xffffffffU
#define YELLOW	0xffffff00U
#define GREEN	0xff00ff00U

extern volatile uint32_t *con_fb;

void con_clear(uint32_t bg);
void con_skip(void);
void con_str(const char *label, const char *s);
void con_hex(const char *label, uint64_t v);
/* label, then "a=xxxxxxxx b=xxxxxxxx" style pairs of 32-bit values */
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb);
