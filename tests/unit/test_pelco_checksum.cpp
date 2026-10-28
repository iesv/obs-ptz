/* Golden wire checksums from the Pelco D/P formats.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <catch_amalgamated.hpp>
#include "../../src/drivers/pelco/pelco-protocol.hpp"

TEST_CASE("D checksum is an unsigned eight-bit sum", "[pelco]")
{
	const char diagonal[] = {0x01, 0x00, 0x12, 0x3f, 0x3f};
	REQUIRE(pelco_checksum(diagonal, sizeof(diagonal), true) == 0x91);
	const char rollover[] = {0x0a, char(0x88), char(0x90), 0x00, 0x20};
	REQUIRE(pelco_checksum(rollover, sizeof(rollover), true) == 0x42);
	const char stop[] = {0x01, 0x00, 0x00, 0x00, 0x00};
	REQUIRE(pelco_checksum(stop, sizeof(stop), true) == 0x01);
}

TEST_CASE("P checksum includes both sync bytes", "[pelco]")
{
	const char frame[] = {char(0xa0), 0x00, 0x00, 0x12, 0x01, 0x00, char(0xaf)};
	REQUIRE(pelco_checksum(frame, sizeof(frame), false) == 0x1c);
}
