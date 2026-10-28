/* Pelco checksum over the payload, without the sync byte for D, with it for P.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#pragma once
#include <cstddef>
#include <cstdint>

/* This helper is independent of OBS and Qt so golden protocol vectors test
 * the same encoder used by the driver, rather than a simulator that copies
 * the driver's mistakes.
 *
 * D uses the arithmetic sum modulo 256, NOT decimal 100. Treat each char as
 * an unsigned wire byte before adding it: char may be signed on the host.
 * P uses XOR over its supplied start marker, payload and end marker.
 * Converting the final unsigned result to uint8_t keeps exactly its low eight
 * bits, implementing D's modulo operation without a separate division. */
inline uint8_t pelco_checksum(const char *data, size_t size, bool pelcoD)
{
	unsigned int checksum = 0;
	for (size_t i = 0; i < size; ++i) {
		auto byte = static_cast<uint8_t>(data[i]);
		checksum = pelcoD ? checksum + byte : checksum ^ byte;
	}
	return static_cast<uint8_t>(checksum);
}
