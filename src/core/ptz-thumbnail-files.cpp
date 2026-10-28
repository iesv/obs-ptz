/* Pan Tilt Zoom Controls - preset thumbnail files
 *
 * Copyright 2026 Grant Likely <grant.likely@secretlab.ca>
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include <obs-module.h>
#include <obs.hpp>
#include <graphics/graphics.h>
#include <graphics/vec4.h>
#include <memory>
#include <algorithm>
#include <QDir>
#include <QFileInfo>
#include <QPointer>
#include <QFile>
#include <QMetaObject>
#include <QUuid>
#include "ptz-thumbnail-files.hpp"

/* ptz-thumbnail-sweep.cpp's thumbnailDirectory() is the same directory */
QString ptz_thumbnail_dir()
{
	char *path = obs_module_config_path("thumbnails");
	if (!path)
		return QString();
	QString dir = QString::fromUtf8(path);
	bfree(path);
	/* Portable OBS may return ../../config/... relative to its bin folder.
	 * Resolve that inside the OBS process before exposing paths to the UI
	 * or API clients, whose current working directory may be different. */
	return QDir(dir).absolutePath();
}

QString ptz_thumbnail_path(const QString &fileName)
{
	if (fileName.isEmpty() || fileName != QFileInfo(fileName).fileName())
		return QString();
	QString dir = ptz_thumbnail_dir();
	return dir.isEmpty() ? QString() : QDir(dir).filePath(fileName);
}

QString ptz_thumbnail_new_name(const QString &owner, const QString &suffix)
{
	QString name = QUuid::createUuid().toString(QUuid::WithoutBraces) + "." + suffix;
	return owner.isEmpty() ? name : owner + "_" + name;
}

QString ptz_thumbnail_owner(const QString &fileName)
{
	int end = fileName.indexOf('_');
	return end < 0 ? QString() : fileName.left(end);
}

QString ptz_thumbnail_write(const QImage &image, const QString &owner)
{
	if (image.isNull())
		return QString();
	QDir().mkpath(ptz_thumbnail_dir());
	/* JPEG is much smaller, but not every Qt build ships the plugin */
	for (const char *ext : {"jpg", "png"}) {
		QString name = ptz_thumbnail_new_name(owner, ext);
		QString path = ptz_thumbnail_path(name);
		if (!path.isEmpty() && image.save(path, ext, 85))
			return name;
	}
	return QString();
}

void ptz_thumbnail_remove(const QString &fileName)
{
	QString path = ptz_thumbnail_path(fileName);
	if (!path.isEmpty())
		QFile::remove(path);
}

namespace {

struct CaptureJob {
	OBSWeakSource source;
	QPointer<QObject> context;
	std::function<void(QImage)> callback;
};

/* Runs on the graphics thread */
QImage renderSource(obs_source_t *source)
{
	uint32_t srcWidth = obs_source_get_base_width(source);
	uint32_t srcHeight = obs_source_get_base_height(source);
	if (!srcWidth || !srcHeight)
		return QImage();

	/* Bound BOTH dimensions. Limiting only the width makes a tall text or
	 * portrait source allocate an unexpectedly large render target and CPU
	 * staging surface. Scale by the longest edge, keep the aspect ratio and
	 * retain at least one pixel for extremely narrow sources. Products use
	 * 64-bit arithmetic so the dimension calculation itself cannot overflow. */
	uint32_t longest = std::max(srcWidth, srcHeight);
	uint32_t limit = std::min<uint32_t>(PTZ_THUMBNAIL_WIDTH, longest);
	uint32_t width = std::max<uint32_t>(1, (uint64_t)srcWidth * limit / longest);
	uint32_t height = std::max<uint32_t>(1, (uint64_t)srcHeight * limit / longest);

	QImage image;
	obs_enter_graphics();
	gs_texrender_t *texrender = gs_texrender_create(GS_BGRA, GS_ZS_NONE);
	gs_stagesurf_t *stage = gs_stagesurface_create(width, height, GS_BGRA);
	/* Allocation failure must leave the existing preset image intact. An
	 * empty result is deliberately ignored by setPresetThumbnail(), rather
	 * than replacing a good thumbnail with a missing or invalid image. */
	if (!texrender || !stage) {
		blog(LOG_WARNING, "[obs-ptz] could not allocate thumbnail capture resources (%ux%u)", width, height);
		gs_stagesurface_destroy(stage);
		gs_texrender_destroy(texrender);
		obs_leave_graphics();
		return image;
	}

	gs_texrender_reset(texrender);
	if (gs_texrender_begin(texrender, width, height)) {
		vec4 clear;
		vec4_zero(&clear);
		gs_clear(GS_CLEAR_COLOR, &clear, 0.0f, 0);
		gs_ortho(0.0f, (float)srcWidth, 0.0f, (float)srcHeight, -100.0f, 100.0f);

		gs_blend_state_push();
		gs_blend_function(GS_BLEND_ONE, GS_BLEND_ZERO);
		obs_source_inc_showing(source);
		obs_source_video_render(source);
		obs_source_dec_showing(source);
		gs_blend_state_pop();
		gs_texrender_end(texrender);

		gs_stage_texture(stage, gs_texrender_get_texture(texrender));
		uint8_t *data = nullptr;
		uint32_t linesize = 0;
		if (gs_stagesurface_map(stage, &data, &linesize)) {
			/* BGRA in memory is Format_ARGB32 on little-endian, which
			 * is every platform OBS runs on. Copy: the mapping goes away
			 * below. */
			image = QImage(data, width, height, linesize, QImage::Format_ARGB32)
					.convertToFormat(QImage::Format_RGB32);
			gs_stagesurface_unmap(stage);
		} else {
			/* Keep readback failures distinguishable from a UI-only white
			 * preview when diagnosing graphics-driver-specific reports.
			 * The same empty-result rule preserves any previous thumbnail. */
			blog(LOG_WARNING, "[obs-ptz] could not read back the preset thumbnail for '%s'",
			     obs_source_get_name(source));
		}
	}
	gs_stagesurface_destroy(stage);
	gs_texrender_destroy(texrender);
	obs_leave_graphics();
	return image;
}

void captureTask(void *param)
{
	std::unique_ptr<CaptureJob> job(static_cast<CaptureJob *>(param));
	QImage image;
	OBSSourceAutoRelease source = obs_weak_source_get_source(job->source);
	if (source)
		image = renderSource(source);

	QObject *context = job->context;
	if (!context)
		return;
	auto callback = std::move(job->callback);
	QMetaObject::invokeMethod(context, [callback, image] { callback(image); }, Qt::QueuedConnection);
}

} // namespace

void ptz_capture_source_thumbnail(obs_source_t *source, QObject *context, std::function<void(QImage)> callback)
{
	if (!source || !context || !callback)
		return;
	auto *job = new CaptureJob{OBSGetWeakRef(source), context, std::move(callback)};
	obs_queue_task(OBS_TASK_GRAPHICS, captureTask, job, false);
}
