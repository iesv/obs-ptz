/* Exercise the actual preview renderer with deliberately inherited state.
 * This helper is compiled only into the test plugin, never the shipped one.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "ui-test-harness.hpp"
#include "../../src/controller/ptz-source-preview-render.hpp"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <cstring>

namespace {

/* Read the target drawn by the production helper, without another source
 * render that could independently correct its matrix or blend state. */
QJsonArray pixel(gs_stagesurf_t *stage, gs_texture_t *texture, uint32_t x, uint32_t y)
{
	gs_stage_texture(stage, texture);
	uint8_t *data = nullptr;
	uint32_t stride = 0;
	if (!gs_stagesurface_map(stage, &data, &stride))
		return {};
	const uint8_t *p = data + size_t(y) * stride + size_t(x) * 4;
	QJsonArray result{int(p[2]), int(p[1]), int(p[0])};
	gs_stagesurface_unmap(stage);
	return result;
}

void run(const QMap<QString, QString> &params)
{
	OBSSourceAutoRelease source = obs_get_source_by_name(qUtf8Printable(params.value("source")));
	QJsonObject result;
	constexpr uint32_t width = 128, height = 72;
	obs_enter_graphics();
	gs_texrender_t *target = gs_texrender_create(GS_BGRA, GS_ZS_NONE);
	gs_stagesurf_t *stage = gs_stagesurface_create(width, height, GS_BGRA);
	const uint8_t transparent[4] = {0, 0, 0, 0};
	const uint8_t *pixels = transparent;
	gs_texture_t *marker = gs_texture_create(1, 1, GS_BGRA, 1, &pixels, 0);
	if (source && target && stage && marker && gs_texrender_begin(target, width, height)) {
		vec4 green;
		vec4_set(&green, 0.0f, 1.0f, 0.0f, 1.0f);
		gs_clear(GS_CLEAR_COLOR, &green, 0.0f, 0);
		gs_matrix_push();
		if (params.value("mode") == "matrix")
			gs_matrix_translate3f(5000.0f, 5000.0f, 0.0f);
		matrix4 before, after;
		gs_matrix_get(&before);
		gs_blend_state_push();
		/* Make alpha compositing necessary even when the inherited matrix
		 * is already identity. The transparent source must leave green. */
		gs_enable_blending(false);
		gs_blend_function(GS_BLEND_ONE, GS_BLEND_ZERO);
		ptz_render_source_preview(source, width, height);
		gs_matrix_get(&after);
		result["matrix_restored"] = std::memcmp(&before, &after, sizeof(before)) == 0;
		gs_texture_t *texture = gs_texrender_get_texture(target);
		result["corner"] = pixel(stage, texture, 8, 8);
		result["center"] = pixel(stage, texture, width / 2, height / 2);

		/* With the caller's disabled blending restored, a transparent black
		 * sprite overwrites green with black. Leaking enabled blending would
		 * leave it green, independently exposing a missing state restore. */
		gs_matrix_identity();
		gs_ortho(0.0f, float(width), 0.0f, float(height), -100.0f, 100.0f);
		gs_set_viewport(0, 0, width, height);
		gs_effect_t *effect = obs_get_base_effect(OBS_EFFECT_DEFAULT);
		gs_effect_set_texture(gs_effect_get_param_by_name(effect, "image"), marker);
		while (gs_effect_loop(effect, "Draw"))
			gs_draw_sprite(marker, 0, 4, 4);
		result["caller_pixel"] = pixel(stage, texture, 1, 1);
		gs_blend_state_pop();
		gs_matrix_pop();
		gs_texrender_end(target);
	}
	gs_texture_destroy(marker);
	if (stage)
		gs_stagesurface_destroy(stage);
	gs_texrender_destroy(target);
	obs_leave_graphics();
	blog(LOG_INFO, "[ptz-ui-test] preview_render: %s",
	     QJsonDocument(result).toJson(QJsonDocument::Compact).constData());
}

} // namespace

void registerPreviewRenderTest(PTZUITestHarness *harness)
{
	harness->registerTest("preview_render", run);
}
