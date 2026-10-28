/* Pelco checksum over the payload, without the sync byte for D, with it for P.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#pragma once
#include <cstddef>
#include <cstdint>

inline uint8_t pelco_checksum(const char *data, size_t size, bool pelcoD)
{
	unsigned int checksum = 0;
	for (size_t i = 0; i < size; ++i) {
		auto byte = static_cast<uint8_t>(data[i]);
		checksum = pelcoD ? checksum + byte : checksum ^ byte;
	}
	return static_cast<uint8_t>(checksum);
}
