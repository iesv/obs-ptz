/* Native OBS display checks. These requests exist only in the test driver;
 * neither the driver nor its GPU readback code is installed with obs-ptz.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "ui-driver-objects.hpp"
#include "ui-driver.hpp"
#include "../../shared/qt/display/OBSQTDisplay.hpp"

#include <QWindow>
#include <chrono>
#include <condition_variable>
#include <mutex>

#ifdef _WIN32
#include <d3d11.h>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

namespace {

struct FrameProbe {
	std::mutex mutex;
	std::condition_variable ready;
	bool done = false;
	QJsonObject result;
};

/* Appended after the widget's real draw callback. Read the actual native
 * display render target, not GetSourceScreenshot's independent render pass.
 * A source screenshot can be correct while this window is completely white.
 * This callback observes pixels without changing OBS's bound graphics state. */
void probeFrame(void *param, uint32_t cx, uint32_t cy)
{
	auto &probe = *static_cast<FrameProbe *>(param);
	std::lock_guard<std::mutex> lock(probe.mutex);
	if (probe.done)
		return;
	probe.done = true;
	auto finish = [&](QJsonObject result) {
		probe.result = result;
		probe.ready.notify_one();
	};
	if (gs_get_device_type() != GS_DEVICE_DIRECT3D_11) {
		finish(error("unsupported", "native pixel probe requires Direct3D 11"));
		return;
	}
	auto *device = static_cast<ID3D11Device *>(gs_get_device_obj());
	ComPtr<ID3D11DeviceContext> context;
	device->GetImmediateContext(&context);
	ComPtr<ID3D11RenderTargetView> view;
	context->OMGetRenderTargets(1, &view, nullptr);
	if (!view) {
		finish(error("no_frame", "native display has no bound render target"));
		return;
	}
	ComPtr<ID3D11Resource> resource;
	view->GetResource(&resource);
	ComPtr<ID3D11Texture2D> texture;
	if (FAILED(resource.As(&texture))) {
		finish(error("no_frame", "native target is not a 2D texture"));
		return;
	}
	D3D11_TEXTURE2D_DESC desc;
	texture->GetDesc(&desc);
	if (desc.Width != cx || desc.Height != cy || !cx || !cy || desc.SampleDesc.Count != 1 ||
	    (desc.Format != DXGI_FORMAT_B8G8R8A8_UNORM && desc.Format != DXGI_FORMAT_B8G8R8A8_UNORM_SRGB &&
	     desc.Format != DXGI_FORMAT_R8G8B8A8_UNORM && desc.Format != DXGI_FORMAT_R8G8B8A8_UNORM_SRGB)) {
		finish(error("no_frame", "unexpected native display dimensions or pixel format"));
		return;
	}
	desc.Usage = D3D11_USAGE_STAGING;
	desc.BindFlags = 0;
	desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
	desc.MiscFlags = 0;
	ComPtr<ID3D11Texture2D> staging;
	if (FAILED(device->CreateTexture2D(&desc, nullptr, &staging))) {
		finish(error("no_frame", "could not allocate native display readback"));
		return;
	}
	context->CopyResource(staging.Get(), texture.Get());
	D3D11_MAPPED_SUBRESOURCE mapped;
	if (FAILED(context->Map(staging.Get(), 0, D3D11_MAP_READ, 0, &mapped))) {
		finish(error("no_frame", "could not map native display readback"));
		return;
	}
	uint64_t white = 0, dark = 0;
	for (uint32_t y = 0; y < cy; y++) {
		const auto *row = static_cast<const uint8_t *>(mapped.pData) + y * mapped.RowPitch;
		for (uint32_t x = 0; x < cx; x++) {
			const auto *pixel = row + x * 4;
			white += pixel[0] > 240 && pixel[1] > 240 && pixel[2] > 240;
			dark += pixel[0] < 120 && pixel[1] < 120 && pixel[2] < 120;
		}
	}
	context->Unmap(staging.Get(), 0);
	const double pixels = double(cx) * cy;
	finish({{"width", int(cx)}, {"height", int(cy)}, {"white", white / pixels}, {"dark", dark / pixels}});
}

} // namespace
#endif

void addDisplayRequests()
{
	addRequest("native_display", [](const QJsonObject &request) -> QJsonObject {
		Found found = resolve(request["path"]);
		if (!found.error.isEmpty())
			return found.error;
		auto *widget = qobject_cast<QWidget *>(found.objects.first());
		/* The display accessor is inline. Avoid linking against another
		 * plugin's C++ symbols; verify the Qt inheritance before the cast. */
		if (!widget || !widget->inherits("OBSQTDisplay"))
			return error("bad_request", "widget is not an OBSQTDisplay");
		auto *displayWidget = static_cast<OBSQTDisplay *>(widget);
		if (request["recreate"].toBool()) {
			/* Exercise the real Qt surface lifecycle, as occurs on native
			 * window reparenting. Destruction must release the old swap chain
			 * without permanently preventing the next display from opening. */
			QWindow *window = widget->windowHandle();
			window->destroy();
			window->create();
			window->show();
			widget->update();
			return {};
		}
		obs_display_t *display = displayWidget->GetDisplay();
		if (!display || !obs_display_enabled(display))
			return error("no_frame", "native display is missing or disabled");
#ifdef _WIN32
		FrameProbe probe;
		obs_display_add_draw_callback(display, probeFrame, &probe);
		{
			std::unique_lock<std::mutex> lock(probe.mutex);
			probe.ready.wait_for(lock, std::chrono::seconds(1), [&]() { return probe.done; });
		}
		/* Remove outside the probe mutex: removal waits for an executing
		 * callback. The main thread retains the widget during this request,
		 * and removal completes before stack-owned callback data goes away. */
		obs_display_remove_draw_callback(display, probeFrame, &probe);
		return probe.done ? probe.result : error("no_frame", "native display did not draw a frame");
#else
		return error("unsupported", "native pixel probe currently requires Windows");
#endif
	});
}
