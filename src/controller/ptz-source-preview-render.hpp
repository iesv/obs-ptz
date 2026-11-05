/* Source preview rendering shared by the widget and its graphics regression.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#pragma once

#include <obs-module.h>
#include "../../shared/qt/display/display-helpers.hpp"

/* Called inside OBS's graphics context. A display is an independent view of
 * the source, so it must not inherit a previous render pass's model matrix
 * or blend settings. Restore the caller's state before returning. */
inline void ptz_render_source_preview(obs_source_t *source, uint32_t cx, uint32_t cy)
{
	if (!source || !cx || !cy)
		return;
	uint32_t sourceCX = obs_source_get_width(source);
	uint32_t sourceCY = obs_source_get_height(source);
	if (!sourceCX || !sourceCY)
		return;

	int x, y;
	float scale;
	GetScaleAndCenterPos(sourceCX, sourceCY, cx, cy, x, y, scale);
	int newCX = int(scale * float(sourceCX));
	int newCY = int(scale * float(sourceCY));

	gs_viewport_push();
	gs_projection_push();
	gs_matrix_push();
	gs_matrix_identity();
	const bool previous = gs_set_linear_srgb(true);
	gs_ortho(0.0f, float(sourceCX), 0.0f, float(sourceCY), -100.0f, 100.0f);
	gs_set_viewport(x, y, newCX, newCY);
	/* OBS sources use premultiplied alpha. In particular, transparent text
	 * must composite over the preview background rather than replace it. */
	gs_blend_state_push();
	gs_enable_blending(true);
	gs_blend_function(GS_BLEND_ONE, GS_BLEND_INVSRCALPHA);
	obs_source_video_render(source);
	gs_blend_state_pop();
	gs_set_linear_srgb(previous);
	gs_matrix_pop();
	gs_projection_pop();
	gs_viewport_pop();
}
