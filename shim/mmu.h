#pragma once
#include <stdint.h>

#define FB_PHYS	0xdfc00000UL	/* haydn cont_splash_region; sweet's 0x9c000000 is a different board */

struct mmu_info {
	uint64_t img_lo, img_hi, ttbr;
	uint64_t sctlr_before, sctlr_after;
	int n_l3;
};

int mmu_enable(struct mmu_info *info);
uint64_t mmu_probe(uintptr_t va);
