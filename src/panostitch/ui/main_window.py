from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QThread, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from panostitch.core.panorama_stitch import PanoramaStitchSettings
from panostitch.core.panorama_preview_cache import (
    build_panorama_cache_key,
    clear_panorama_preview_cache,
    load_panorama_preview_cache,
    save_panorama_preview_cache,
)
from panostitch.core.render_backend import current_render_backend
from panostitch.core.render_pipeline import render_panorama_adjusted_rgb, scaled_frame_to_bounds
from panostitch.domain.models import CorrectionPreset, ExportOptions, FrameGeometry, ImageAsset
from panostitch.io.image_loader import LoadedImage, load_image, read_image_asset_metadata, save_rgb_image, scan_directory_assets
from panostitch.io.lens_db import build_seed_preset_from_match, find_lens_database_match
from panostitch.io.profile_catalog import sony_a7r3_sigma_15mm_preset
from panostitch.ui.detached_preview_window import DetachedPreviewWindow
from panostitch.ui.export_progress_dialog import ExportProgressDialog
from panostitch.ui.export_worker import ExportWorker
from panostitch.ui.panorama_progress_dialog import PanoramaProgressDialog
from panostitch.ui.panorama_worker import PanoramaRenderRequest, PanoramaWorker
from panostitch.ui.preview_canvas import PreviewCanvas
from panostitch.ui.preview_worker import PreviewRenderRequest, PreviewWorker
from panostitch.ui.resettable_slider import ResettableSlider


def enum_value(value) -> int:
    return int(getattr(value, "value", value))


class MainWindow(QMainWindow):
    preview_render_requested = Signal(object)
    panorama_render_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PanoStitch")
        self.resize(1520, 900)
        self.setMinimumSize(1180, 720)

        self.default_preset = sony_a7r3_sigma_15mm_preset()
        self.base_preset = self.default_preset
        self.loaded_preview_cache: dict[Path, LoadedImage] = {}
        self.image_assets: list[ImageAsset] = []
        self.current_loaded_image: LoadedImage | None = None
        self.current_rendered_image = None
        self.current_metrics_text = "No preview rendered yet."
        self.adjust_controls: dict[str, QDoubleSpinBox] = {}
        self.adjust_value_labels: dict[str, QLabel] = {}
        self.control_defaults: dict[str, float] = {}
        self.export_thread: QThread | None = None
        self.export_worker: ExportWorker | None = None
        self.export_dialog: ExportProgressDialog | None = None
        self.pending_export_scope = "batch"
        self.pending_export_output_dir: Path | None = None
        self.detached_preview_window: DetachedPreviewWindow | None = None
        self.preview_render_thread: QThread | None = None
        self.preview_render_worker: PreviewWorker | None = None
        self.preview_render_busy = False
        self.pending_preview_request: PreviewRenderRequest | None = None
        self.preview_request_serial = 0
        self.panorama_assets: list[ImageAsset] = []
        self.current_panorama_image = None
        self.current_panorama_base_image = None
        self.current_panorama_base_metrics: dict | None = None
        self.current_panorama_input_names: list[str] = []
        self.current_panorama_used_precorrection = False
        self.current_panorama_metrics_text = "No panorama preview rendered yet."
        self.panorama_adjust_controls: dict[str, QDoubleSpinBox] = {}
        self.panorama_adjust_value_labels: dict[str, QLabel] = {}
        self.panorama_control_defaults: dict[str, float] = {}
        self.panorama_render_thread: QThread | None = None
        self.panorama_render_worker: PanoramaWorker | None = None
        self.panorama_render_busy = False
        self.panorama_request_serial = 0
        self.panorama_progress_dialog: PanoramaProgressDialog | None = None
        self.render_backend = current_render_backend()
        self.preview_source_max_edge = 4096
        self._clear_panorama_preview_cache()
        self.panorama_default_preset = replace(
            self.default_preset,
            name="Panorama correction",
            output_projection="rectilinear",
            horizontal_fov_deg=120.0,
            yaw_deg=0.0,
            pitch_deg=0.0,
            roll_deg=0.0,
            zoom=1.0,
            vertical_shift=0.0,
            post_rotate_deg=0.0,
            curve_straighten=0.0,
            safe_margin=0.0,
            notes="Post-stitch preview correction.",
        )

        self.interaction_hint = (
            "Left drag adjusts pitch, yaw, vertical offset and lens FOV around the grabbed area. Middle drag shifts the image vertically. Right drag or Shift+drag rotates and offsets. "
            "Wheel zooms the preview view. Ctrl+Wheel changes correction zoom. Shift+Wheel changes lens FOV. Alt+Wheel changes crop."
        )

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(45)
        self.render_timer.timeout.connect(self.render_preview)
        self.preview_resize_timer = QTimer(self)
        self.preview_resize_timer.setSingleShot(True)
        self.preview_resize_timer.setInterval(180)
        self.preview_resize_timer.timeout.connect(self.render_preview)
        self.panorama_adjust_timer = QTimer(self)
        self.panorama_adjust_timer.setSingleShot(True)
        self.panorama_adjust_timer.setInterval(35)
        self.panorama_adjust_timer.timeout.connect(self.render_current_panorama_adjustment)
        self._setup_preview_worker()
        self._setup_panorama_worker()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_preview_worker)
            app.aboutToQuit.connect(self._shutdown_panorama_worker)
            app.aboutToQuit.connect(self._clear_panorama_preview_cache)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_workspaces(), 1)
        self.setCentralWidget(root)

        self.statusBar().showMessage("Select an image folder to start.")
        self.output_dir_edit.setText(str(Path("/run/media/stolpee/localprog/panostitch/exports")))
        self._apply_preset_to_controls(self.base_preset)
        self._update_export_summary()
        self._update_panorama_export_summary()

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(188)
        sidebar.setMaximumWidth(188)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(8)

        title = QLabel("PanoStitch")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        self.step_group = QButtonGroup(self)
        self.step_group.setExclusive(True)
        self.step_group.idClicked.connect(self.on_step_selected)

        for index, step_name in enumerate(("Fisheye Correct", "Panorama Stitch", "Lens Profiles", "Batch Export"), start=1):
            layout.addWidget(self._build_step_button(index, step_name))

        layout.addStretch(1)
        return sidebar

    def _build_workspaces(self) -> QWidget:
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self._build_fisheye_workspace())
        self.workspace_stack.addWidget(self._build_panorama_workspace())
        self.workspace_stack.addWidget(
            self._build_placeholder_workspace(
                "Lens Profiles",
                "Lens Profiles will collect bundled lens DB entries, manual calibration notes and future profile switching.\n\n"
                "Use Fisheye Correct for the active Sigma workflow today.",
            )
        )
        self.workspace_stack.addWidget(
            self._build_placeholder_workspace(
                "Batch Export",
                "Batch export for fisheye correction lives in the Fisheye Correct workspace.\n\n"
                "Panorama export currently lives in Panorama Stitch after a preview has been built.",
            )
        )
        return self.workspace_stack

    def _build_step_button(self, index: int, name: str) -> QWidget:
        button = QPushButton(name)
        button.setObjectName("SidebarNavButton")
        button.setCheckable(True)
        if index == 1:
            button.setChecked(True)
        self.step_group.addButton(button, index)
        return button

    def _set_tooltip(self, widget: QWidget, text: str) -> None:
        widget.setToolTip(text)

    def _set_label_and_control_tooltip(self, label: QLabel, control: QWidget, text: str) -> None:
        label.setToolTip(text)
        control.setToolTip(text)

    def _build_fisheye_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.import_panel = self._build_import_panel()
        self.adjust_panel = self._build_adjust_panel()
        self.preview_panel = self._build_preview_panel()
        self.preview_info_panel = self._build_preview_info_panel()
        self.export_panel = self._build_export_panel()

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.setHandleWidth(10)
        top_splitter.addWidget(self.import_panel)
        top_splitter.addWidget(self.adjust_panel)
        top_splitter.addWidget(self.preview_panel)
        top_splitter.setStretchFactor(0, 5)
        top_splitter.setStretchFactor(1, 5)
        top_splitter.setStretchFactor(2, 6)
        layout.addWidget(top_splitter, 3)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)
        bottom_splitter.setHandleWidth(10)
        bottom_splitter.addWidget(self.preview_info_panel)
        bottom_splitter.addWidget(self.export_panel)
        bottom_splitter.setStretchFactor(0, 1)
        bottom_splitter.setStretchFactor(1, 1)
        layout.addWidget(bottom_splitter, 2)
        return workspace

    def _build_placeholder_workspace(self, title_text: str, body_text: str) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        panel, panel_layout = self._make_panel(title_text)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(body_text)
        panel_layout.addWidget(text, 1)
        layout.addWidget(panel, 1)
        return workspace

    def _build_panorama_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.panorama_import_panel = self._build_panorama_import_panel()
        self.panorama_settings_panel = self._build_panorama_settings_panel()
        self.panorama_preview_panel = self._build_panorama_preview_panel()
        self.panorama_status_panel = self._build_panorama_status_panel()
        self.panorama_export_panel = self._build_panorama_export_panel()

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)
        top_splitter.setHandleWidth(10)
        top_splitter.addWidget(self.panorama_import_panel)
        top_splitter.addWidget(self.panorama_settings_panel)
        top_splitter.addWidget(self.panorama_preview_panel)
        top_splitter.setStretchFactor(0, 5)
        top_splitter.setStretchFactor(1, 4)
        top_splitter.setStretchFactor(2, 6)
        layout.addWidget(top_splitter, 3)

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)
        bottom_splitter.setHandleWidth(10)
        bottom_splitter.addWidget(self.panorama_status_panel)
        bottom_splitter.addWidget(self.panorama_export_panel)
        bottom_splitter.setStretchFactor(0, 1)
        bottom_splitter.setStretchFactor(1, 1)
        layout.addWidget(bottom_splitter, 2)
        return workspace

    def _build_panorama_import_panel(self) -> QWidget:
        panel, layout = self._make_panel("Panorama Import")
        panel.setMinimumWidth(372)

        self.panorama_source_dir_edit = QLineEdit()
        self.panorama_source_dir_edit.setPlaceholderText("Choose a folder with overlapping images")
        self._set_tooltip(
            self.panorama_source_dir_edit,
            "Folder with the overlapping images that should be stitched into one panorama.",
        )
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.choose_panorama_directory)
        self._set_tooltip(browse_button, "Choose a source folder for panorama stitching.")
        load_button = QPushButton("Load folder")
        load_button.clicked.connect(self.load_panorama_directory)
        self._set_tooltip(load_button, "Scan the selected folder and list stitchable images.")
        use_fisheye_button = QPushButton("Use fisheye folder")
        use_fisheye_button.clicked.connect(self.use_current_fisheye_folder_for_panorama)
        self._set_tooltip(
            use_fisheye_button,
            "Copy the currently loaded fisheye folder into the panorama workflow.",
        )

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_row.addWidget(self.panorama_source_dir_edit, 1)
        source_row.addWidget(browse_button)
        source_row.addWidget(load_button)
        source_row.addWidget(use_fisheye_button)

        self.panorama_image_list = QListWidget()
        self.panorama_image_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.panorama_image_list.itemSelectionChanged.connect(self._update_panorama_export_summary)
        self.panorama_image_list.itemSelectionChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_image_list,
            "Select the overlapping images to include in the panorama preview and export.",
        )

        select_row = QHBoxLayout()
        select_row.setSpacing(8)
        select_all_button = QPushButton("Select all")
        clear_button = QPushButton("Clear")
        select_all_button.clicked.connect(self.select_all_panorama_images)
        clear_button.clicked.connect(self.panorama_image_list.clearSelection)
        self._set_tooltip(select_all_button, "Select all loaded panorama candidates.")
        self._set_tooltip(clear_button, "Clear the current panorama image selection.")
        select_row.addWidget(select_all_button)
        select_row.addWidget(clear_button)
        select_row.addStretch(1)

        source_label = QLabel("Source folder")
        source_label.setToolTip("Folder with the overlapping images that should be stitched into one panorama.")
        layout.addWidget(source_label)
        layout.addLayout(source_row)
        layout.addLayout(select_row)
        layout.addWidget(self.panorama_image_list, 1)
        return panel

    def _build_panorama_settings_panel(self) -> QWidget:
        panel, body_layout = self._make_panel("Stitch Settings")
        panel.setMinimumWidth(336)

        scroll = QScrollArea()
        scroll.setObjectName("AdjustScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 16, 0)
        content_layout.setSpacing(10)

        self.panorama_precorrect_checkbox = QCheckBox("Pre-correct fisheye with active preset")
        self.panorama_precorrect_checkbox.setChecked(True)
        self.panorama_precorrect_checkbox.stateChanged.connect(self._update_panorama_export_summary)
        self.panorama_precorrect_checkbox.stateChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_precorrect_checkbox,
            "Apply the current fisheye correction preset to each image before stitching. Useful for fisheye series, but it can also make matching harder if the preset is off.",
        )

        self.panorama_mode_combo = QComboBox()
        self.panorama_mode_combo.addItems(["panorama", "scans"])
        self.panorama_mode_combo.currentTextChanged.connect(self._update_panorama_export_summary)
        self.panorama_mode_combo.currentTextChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_mode_combo,
            "Panorama is the normal rotating-camera mode. Scans is better for flatter captures such as documents or near-planar scenes.",
        )

        self.panorama_max_edge_spin = QSpinBox()
        self.panorama_max_edge_spin.setRange(960, 4096)
        self.panorama_max_edge_spin.setSingleStep(160)
        self.panorama_max_edge_spin.setValue(1800)
        self.panorama_max_edge_spin.valueChanged.connect(self._update_panorama_export_summary)
        self.panorama_max_edge_spin.valueChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_max_edge_spin,
            "Preview input size per image. Higher values can improve matching and detail, but cost more time and GPU/CPU memory.",
        )

        self.panorama_registration_spin = QDoubleSpinBox()
        self.panorama_registration_spin.setRange(0.1, 6.0)
        self.panorama_registration_spin.setDecimals(2)
        self.panorama_registration_spin.setSingleStep(0.1)
        self.panorama_registration_spin.setValue(0.6)
        self.panorama_registration_spin.valueChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_registration_spin,
            "Resolution used when finding and matching features between images. Higher can help difficult image sets, but is slower.",
        )

        self.panorama_seam_spin = QDoubleSpinBox()
        self.panorama_seam_spin.setRange(0.1, 6.0)
        self.panorama_seam_spin.setDecimals(2)
        self.panorama_seam_spin.setSingleStep(0.1)
        self.panorama_seam_spin.setValue(0.3)
        self.panorama_seam_spin.valueChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_seam_spin,
            "Resolution used for seam estimation. Higher values can improve seam placement, but increase processing time.",
        )

        self.panorama_compose_spin = QDoubleSpinBox()
        self.panorama_compose_spin.setRange(0.1, 12.0)
        self.panorama_compose_spin.setDecimals(2)
        self.panorama_compose_spin.setSingleStep(0.1)
        self.panorama_compose_spin.setValue(1.2)
        self.panorama_compose_spin.valueChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_compose_spin,
            "Resolution used when composing the final panorama preview. Higher gives a sharper preview but costs more time.",
        )

        self.panorama_confidence_spin = QDoubleSpinBox()
        self.panorama_confidence_spin.setRange(0.1, 5.0)
        self.panorama_confidence_spin.setDecimals(2)
        self.panorama_confidence_spin.setSingleStep(0.1)
        self.panorama_confidence_spin.setValue(1.0)
        self.panorama_confidence_spin.valueChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_confidence_spin,
            "Minimum confidence OpenCV requires before keeping image relations. Lower values may accept weaker matches; higher values are stricter.",
        )

        self.panorama_wave_checkbox = QCheckBox("Wave correction")
        self.panorama_wave_checkbox.setChecked(True)
        self.panorama_wave_checkbox.stateChanged.connect(self._maybe_restore_cached_panorama_preview)
        self._set_tooltip(
            self.panorama_wave_checkbox,
            "Try to smooth the horizon and overall camera wave in the stitched panorama. Can help some sets and hurt others.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        mode_label = QLabel("Mode")
        self._set_label_and_control_tooltip(
            mode_label,
            self.panorama_mode_combo,
            "Panorama is the normal rotating-camera mode. Scans is better for flatter captures such as documents or near-planar scenes.",
        )
        grid.addWidget(mode_label, 0, 0)
        grid.addWidget(self.panorama_mode_combo, 0, 1)
        max_edge_label = QLabel("Max input edge")
        self._set_label_and_control_tooltip(
            max_edge_label,
            self.panorama_max_edge_spin,
            "Preview input size per image. Higher values can improve matching and detail, but cost more time and GPU/CPU memory.",
        )
        grid.addWidget(max_edge_label, 1, 0)
        grid.addWidget(self.panorama_max_edge_spin, 1, 1)
        registration_label = QLabel("Registration MP")
        self._set_label_and_control_tooltip(
            registration_label,
            self.panorama_registration_spin,
            "Resolution used when finding and matching features between images. Higher can help difficult image sets, but is slower.",
        )
        grid.addWidget(registration_label, 2, 0)
        grid.addWidget(self.panorama_registration_spin, 2, 1)
        seam_label = QLabel("Seam MP")
        self._set_label_and_control_tooltip(
            seam_label,
            self.panorama_seam_spin,
            "Resolution used for seam estimation. Higher values can improve seam placement, but increase processing time.",
        )
        grid.addWidget(seam_label, 3, 0)
        grid.addWidget(self.panorama_seam_spin, 3, 1)
        compose_label = QLabel("Compose MP")
        self._set_label_and_control_tooltip(
            compose_label,
            self.panorama_compose_spin,
            "Resolution used when composing the final panorama preview. Higher gives a sharper preview but costs more time.",
        )
        grid.addWidget(compose_label, 4, 0)
        grid.addWidget(self.panorama_compose_spin, 4, 1)
        confidence_label = QLabel("Confidence")
        self._set_label_and_control_tooltip(
            confidence_label,
            self.panorama_confidence_spin,
            "Minimum confidence OpenCV requires before keeping image relations. Lower values may accept weaker matches; higher values are stricter.",
        )
        grid.addWidget(confidence_label, 5, 0)
        grid.addWidget(self.panorama_confidence_spin, 5, 1)

        self.panorama_build_button = QPushButton("Build stitch preview")
        self.panorama_build_button.clicked.connect(self.run_panorama_preview)
        self._set_tooltip(
            self.panorama_build_button,
            "Build a panorama preview from the selected images using the current stitch settings.",
        )

        self.panorama_correction_section, correction_layout, self.panorama_correction_content, self.panorama_correction_toggle = self._make_collapsible_section(
            "Panorama correction",
            expanded=True,
        )
        self._set_tooltip(
            self.panorama_correction_toggle,
            "Show or hide the post-stitch correction controls used to refine the stitched preview.",
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Pitch",
                "pitch_deg",
                -120.0,
                120.0,
                0.0,
                1,
                10,
                "Tilts the stitched panorama up or down inside the preview frame.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Roll",
                "roll_deg",
                -180.0,
                180.0,
                0.0,
                1,
                10,
                "Levels the stitched panorama by rotating the virtual view.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Yaw",
                "yaw_deg",
                -180.0,
                180.0,
                0.0,
                1,
                10,
                "Moves the stitched panorama left or right inside the preview frame.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Rotate image",
                "post_rotate_deg",
                -180.0,
                180.0,
                0.0,
                1,
                10,
                "Applies a final image rotation after the panorama has been stitched.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Zoom",
                "zoom",
                0.20,
                4.00,
                1.0,
                2,
                100,
                "Controls how tight the post-stitched view is. Higher values crop further in.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Vertical shift",
                "vertical_shift",
                -2.00,
                2.00,
                0.0,
                3,
                1000,
                "Moves the stitched panorama up or down without rebuilding the stitch.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Horizontal FOV",
                "horizontal_fov_deg",
                20.0,
                175.0,
                120.0,
                1,
                10,
                "Changes how wide the stitched panorama view feels. Lower values look tighter; higher values look wider.",
            )
        )
        correction_layout.addLayout(
            self._build_panorama_slider_row(
                "Crop margin",
                "safe_margin",
                0.00,
                0.35,
                0.0,
                3,
                1000,
                "Shrinks the visible area to hide edge artifacts or black borders after stitch correction.",
            )
        )

        content_layout.addWidget(self.panorama_precorrect_checkbox)
        content_layout.addWidget(self.panorama_wave_checkbox)
        content_layout.addLayout(grid)
        content_layout.addWidget(self.panorama_correction_section)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        body_layout.addWidget(scroll, 1)
        body_layout.addWidget(self.panorama_build_button, 0, Qt.AlignmentFlag.AlignBottom)
        return panel

    def _build_panorama_preview_panel(self) -> QWidget:
        panel, layout = self._make_panel("Panorama Preview")
        preview_frame = QFrame()
        preview_frame.setMinimumHeight(360)
        preview_frame.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #121518, stop:1 #1e242b);"
            "border-radius: 12px; border: 1px solid #2b333b;"
        )
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(18, 18, 18, 18)

        self.panorama_preview_label = PreviewCanvas()
        self.panorama_preview_label.clear_preview(
            "Panorama preview\n\n"
            "Load a folder with overlapping frames and build a stitch preview.\n"
            "Wheel zooms the panorama preview view."
        )
        self._set_tooltip(
            self.panorama_preview_label,
            "Panorama preview canvas. Drag directly on the image to refine the post-stitch correction. Wheel zooms the preview view; Ctrl+Wheel changes correction zoom.",
        )
        self.panorama_preview_label.drag_delta.connect(self.on_panorama_preview_drag)
        self.panorama_preview_label.zoom_delta.connect(self.on_panorama_preview_zoom)
        self.panorama_preview_label.reset_requested.connect(self.reset_panorama_preview_adjustments)
        self.panorama_preview_label.viewport_resized.connect(self.schedule_panorama_adjustment)
        preview_layout.addWidget(self.panorama_preview_label, 1)
        layout.addWidget(preview_frame, 1)
        return panel

    def _build_panorama_status_panel(self) -> QWidget:
        panel, layout = self._make_panel("Panorama Info")
        self.panorama_metrics_text = QTextEdit()
        self.panorama_metrics_text.setReadOnly(True)
        self.panorama_metrics_text.setPlainText("No panorama preview rendered yet.")
        layout.addWidget(self.panorama_metrics_text, 1)
        return panel

    def _build_panorama_export_panel(self) -> QWidget:
        panel, layout = self._make_panel("Panorama Export")

        self.panorama_output_dir_edit = QLineEdit()
        self._set_tooltip(
            self.panorama_output_dir_edit,
            "Folder where the stitched panorama export will be written.",
        )
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.choose_panorama_output_directory)
        self._set_tooltip(browse_button, "Choose the panorama export folder.")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.panorama_output_dir_edit, 1)
        row.addWidget(browse_button)

        self.panorama_format_combo = QComboBox()
        self.panorama_format_combo.addItems(["jpeg", "tiff", "png"])
        self.panorama_format_combo.currentTextChanged.connect(self._update_panorama_export_summary)
        self._set_tooltip(
            self.panorama_format_combo,
            "Export format for the current panorama preview.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        panorama_output_label = QLabel("Output folder")
        self._set_label_and_control_tooltip(
            panorama_output_label,
            self.panorama_output_dir_edit,
            "Folder where the stitched panorama export will be written.",
        )
        grid.addWidget(panorama_output_label, 0, 0)
        grid.addLayout(row, 0, 1)
        panorama_format_label = QLabel("Format")
        self._set_label_and_control_tooltip(
            panorama_format_label,
            self.panorama_format_combo,
            "Export format for the current panorama preview.",
        )
        grid.addWidget(panorama_format_label, 1, 0)
        grid.addWidget(self.panorama_format_combo, 1, 1)
        layout.addLayout(grid)

        self.panorama_export_summary = QTextEdit()
        self.panorama_export_summary.setReadOnly(True)
        layout.addWidget(self.panorama_export_summary, 1)

        self.panorama_export_button = QPushButton("Export panorama")
        self.panorama_export_button.clicked.connect(self.export_current_panorama)
        self.panorama_export_button.setEnabled(False)
        self._set_tooltip(
            self.panorama_export_button,
            "Export the currently built panorama preview to the selected folder and format.",
        )
        layout.addWidget(self.panorama_export_button)
        return panel

    def _make_panel(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        return panel, layout

    def _make_collapsible_panel(self, title_text: str, expanded: bool = True) -> tuple[QFrame, QVBoxLayout, QWidget, QToolButton]:
        panel = QFrame()
        panel.setObjectName("PanelCard")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)

        toggle = QToolButton()
        toggle.setObjectName("DisclosureArrow")
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toggle.setAutoRaise(True)
        header.addWidget(toggle)
        layout.addLayout(header)

        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(10)
        body.setVisible(expanded)
        layout.addWidget(body, 1)

        def _update_disclosure_state(checked: bool) -> None:
            toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            body.setVisible(checked)

        toggle.toggled.connect(_update_disclosure_state)
        return panel, body_layout, body, toggle

    def _make_collapsible_section(self, title_text: str, expanded: bool = True) -> tuple[QWidget, QVBoxLayout, QWidget, QToolButton]:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel(title_text)
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)

        toggle = QToolButton()
        toggle.setObjectName("DisclosureArrow")
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toggle.setAutoRaise(True)
        header.addWidget(toggle)
        layout.addLayout(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        body.setVisible(expanded)
        layout.addWidget(body, 0, Qt.AlignmentFlag.AlignTop)

        def _update_disclosure_state(checked: bool) -> None:
            toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            body.setVisible(checked)

        toggle.toggled.connect(_update_disclosure_state)
        return section, body_layout, body, toggle

    def _build_import_panel(self) -> QWidget:
        panel, layout = self._make_panel("Import")
        panel.setMinimumWidth(372)

        self.source_dir_edit = QLineEdit()
        self.source_dir_edit.setPlaceholderText("Choose a folder with RAW or raster images")
        self._set_tooltip(
            self.source_dir_edit,
            "Folder with the images to correct using the current fisheye preset workflow.",
        )
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.choose_source_directory)
        self._set_tooltip(browse_button, "Choose the source folder for fisheye correction.")

        load_button = QPushButton("Load folder")
        load_button.clicked.connect(self.load_source_directory)
        self._set_tooltip(load_button, "Scan the selected folder and list supported source images.")

        self.camera_name_edit = QLineEdit()
        self.camera_name_edit.setPlaceholderText("Loaded from the first image in the folder")
        self._set_tooltip(
            self.camera_name_edit,
            "Normalized camera name from the first image in the folder. This seeds the starting preset.",
        )
        self.lens_name_edit = QLineEdit()
        self.lens_name_edit.setPlaceholderText("Loaded from the first image in the folder")
        self._set_tooltip(
            self.lens_name_edit,
            "Normalized lens name from the first image in the folder. This is used to seed lens-specific defaults.",
        )

        self.image_list = QListWidget()
        self.image_list.currentRowChanged.connect(self.on_image_selection_changed)
        self._set_tooltip(
            self.image_list,
            "Images in the source folder. Select one to preview and fine-tune the active correction preset.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_row.addWidget(self.source_dir_edit, 1)
        source_row.addWidget(browse_button)
        source_row.addWidget(load_button)

        source_label = QLabel("Source folder")
        self._set_label_and_control_tooltip(
            source_label,
            self.source_dir_edit,
            "Folder with the images to correct using the current fisheye preset workflow.",
        )
        grid.addWidget(source_label, 0, 0)
        grid.addLayout(source_row, 0, 1)
        camera_label = QLabel("Camera")
        self._set_label_and_control_tooltip(
            camera_label,
            self.camera_name_edit,
            "Normalized camera name from the first image in the folder. This seeds the starting preset.",
        )
        grid.addWidget(camera_label, 1, 0)
        grid.addWidget(self.camera_name_edit, 1, 1)
        lens_label = QLabel("Lens")
        self._set_label_and_control_tooltip(
            lens_label,
            self.lens_name_edit,
            "Normalized lens name from the first image in the folder. This is used to seed lens-specific defaults.",
        )
        grid.addWidget(lens_label, 2, 0)
        grid.addWidget(self.lens_name_edit, 2, 1)

        layout.addLayout(grid)
        layout.addWidget(self.image_list, 1)
        return panel

    def _build_adjust_panel(self) -> QWidget:
        panel, body_layout = self._make_panel("Adjust")
        panel.setMinimumWidth(438)
        scroll = QScrollArea()
        scroll.setObjectName("AdjustScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 16, 0)
        content_layout.setSpacing(10)

        self.projection_combo = QComboBox()
        self.projection_combo.addItems(["cylindrical", "rectilinear"])
        self.projection_combo.currentTextChanged.connect(self.schedule_preview_update)
        self._set_tooltip(
            self.projection_combo,
            "Output projection. Cylindrical is usually best for panorama-like fisheye correction. Rectilinear behaves more like a normal wide-angle lens.",
        )

        self.mapping_combo = QComboBox()
        self.mapping_combo.addItems(["equisolid", "equidistant", "stereographic", "orthographic"])
        self.mapping_combo.currentTextChanged.connect(self.schedule_preview_update)
        self._set_tooltip(
            self.mapping_combo,
            "Fisheye lens model used when remapping the source image. Choose the one that best matches the lens behavior.",
        )

        projection_label = QLabel("Projection")
        self._set_label_and_control_tooltip(
            projection_label,
            self.projection_combo,
            "Output projection. Cylindrical is usually best for panorama-like fisheye correction. Rectilinear behaves more like a normal wide-angle lens.",
        )
        content_layout.addWidget(projection_label)
        content_layout.addWidget(self.projection_combo)
        mapping_label = QLabel("Fisheye mapping")
        self._set_label_and_control_tooltip(
            mapping_label,
            self.mapping_combo,
            "Fisheye lens model used when remapping the source image. Choose the one that best matches the lens behavior.",
        )
        content_layout.addWidget(mapping_label)
        content_layout.addWidget(self.mapping_combo)

        content_layout.addLayout(
            self._build_slider_row(
                "Pitch",
                "pitch_deg",
                -120.0,
                120.0,
                self.base_preset.pitch_deg,
                1,
                10,
                "Tilts the virtual camera up or down in the corrected result. Useful for lifting or lowering the horizon line.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Roll",
                "roll_deg",
                -180.0,
                180.0,
                self.base_preset.roll_deg,
                1,
                10,
                "Rotates the corrected frame around its center to level the horizon.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Yaw",
                "yaw_deg",
                -180.0,
                180.0,
                self.base_preset.yaw_deg,
                1,
                10,
                "Pans the virtual camera left or right inside the fisheye frame.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Rotate image",
                "post_rotate_deg",
                -180.0,
                180.0,
                self.base_preset.post_rotate_deg,
                1,
                10,
                "Applies a final in-frame rotation after the main remap. Good for fine leveling without changing the mapping.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Zoom",
                "zoom",
                0.20,
                4.00,
                self.base_preset.zoom,
                2,
                100,
                "Controls how tight the corrected view is. Higher zoom crops in more; lower zoom shows more of the fisheye coverage.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Vertical shift",
                "vertical_shift",
                -2.00,
                2.00,
                self.base_preset.vertical_shift,
                3,
                1000,
                "Moves the corrected view up or down without tilting it as much. Useful for horizon placement and framing.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Horizontal FOV",
                "horizontal_fov_deg",
                20.0,
                175.0,
                self.base_preset.horizontal_fov_deg,
                1,
                10,
                "Horizontal field of view of the corrected output. Lower values look tighter; higher values look wider.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Lens diagonal FOV",
                "lens_diagonal_fov_deg",
                120.0,
                240.0,
                self.base_preset.lens.diagonal_fov_deg,
                1,
                10,
                "Assumed diagonal fisheye coverage of the lens. Changing this alters how aggressively the source is unwarped.",
            )
        )
        content_layout.addLayout(
            self._build_slider_row(
                "Crop margin",
                "safe_margin",
                0.00,
                0.35,
                self.base_preset.safe_margin,
                3,
                1000,
                "Shrinks the usable output area to avoid edge artifacts and black borders.",
            )
        )

        self.preset_name_edit = QLineEdit(self.base_preset.name)
        self.preset_name_edit.textChanged.connect(self.schedule_preview_update)
        self._set_tooltip(
            self.preset_name_edit,
            "Name of the current correction preset. This identifies the adjustment recipe you are working with.",
        )
        preset_name_label = QLabel("Preset name")
        self._set_label_and_control_tooltip(
            preset_name_label,
            self.preset_name_edit,
            "Name of the current correction preset. This identifies the adjustment recipe you are working with.",
        )
        content_layout.addWidget(preset_name_label)
        content_layout.addWidget(self.preset_name_edit)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(self.base_preset.notes)
        self.notes_edit.setMaximumHeight(96)
        self.notes_edit.textChanged.connect(self.schedule_preview_update)
        self._set_tooltip(
            self.notes_edit,
            "Free-form notes about the current preset, shooting angle or intended use.",
        )
        notes_label = QLabel("Notes")
        self._set_label_and_control_tooltip(
            notes_label,
            self.notes_edit,
            "Free-form notes about the current preset, shooting angle or intended use.",
        )
        content_layout.addWidget(notes_label)
        content_layout.addWidget(self.notes_edit)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        body_layout.addWidget(scroll, 1)
        return panel

    def _build_slider_row(
        self,
        label_text: str,
        field_name: str,
        minimum: float,
        maximum: float,
        value: float,
        decimals: int,
        scale: int,
        tooltip_text: str,
    ) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(10)

        label = QLabel(label_text)
        value_label = QLabel(self._format_adjust_value(field_name, value, decimals))
        value_label.setObjectName("InlineValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        spin = QDoubleSpinBox(self)
        spin.setObjectName("ValueSpin")
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(1 / scale if scale > 1 else 1)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        slider = ResettableSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(round(minimum * scale)), int(round(maximum * scale)))
        slider.setValue(int(round(value * scale)))
        slider.reset_to_default.connect(lambda widget=spin, default=value: widget.setValue(default))
        for widget in (label, value_label, spin, slider):
            widget.setToolTip(tooltip_text)

        slider.valueChanged.connect(lambda raw, widget=spin, divisor=scale: widget.setValue(raw / divisor))
        spin.valueChanged.connect(lambda current, widget=slider, multiplier=scale: widget.setValue(int(round(current * multiplier))))
        spin.valueChanged.connect(
            lambda current, widget=value_label, name=field_name, places=decimals: widget.setText(
                self._format_adjust_value(name, current, places)
            )
        )
        spin.valueChanged.connect(self.schedule_preview_update)

        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(value_label)

        row.addLayout(header)
        row.addWidget(slider)
        self.adjust_controls[field_name] = spin
        self.adjust_value_labels[field_name] = value_label
        self.control_defaults[field_name] = value
        return row

    def _build_panorama_slider_row(
        self,
        label_text: str,
        field_name: str,
        minimum: float,
        maximum: float,
        value: float,
        decimals: int,
        scale: int,
        tooltip_text: str,
    ) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(10)

        label = QLabel(label_text)
        value_label = QLabel(self._format_adjust_value(field_name, value, decimals))
        value_label.setObjectName("InlineValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        spin = QDoubleSpinBox(self)
        spin.setObjectName("ValueSpin")
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(1 / scale if scale > 1 else 1)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        slider = ResettableSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(round(minimum * scale)), int(round(maximum * scale)))
        slider.setValue(int(round(value * scale)))
        slider.reset_to_default.connect(lambda widget=spin, default=value: widget.setValue(default))
        for widget in (label, value_label, spin, slider):
            widget.setToolTip(tooltip_text)

        slider.valueChanged.connect(lambda raw, widget=spin, divisor=scale: widget.setValue(raw / divisor))
        spin.valueChanged.connect(lambda current, widget=slider, multiplier=scale: widget.setValue(int(round(current * multiplier))))
        spin.valueChanged.connect(
            lambda current, widget=value_label, name=field_name, places=decimals: widget.setText(
                self._format_adjust_value(name, current, places)
            )
        )
        spin.valueChanged.connect(self.schedule_panorama_adjustment)

        header.addWidget(label)
        header.addStretch(1)
        header.addWidget(value_label)

        row.addLayout(header)
        row.addWidget(slider)
        self.panorama_adjust_controls[field_name] = spin
        self.panorama_adjust_value_labels[field_name] = value_label
        self.panorama_control_defaults[field_name] = value
        return row

    def _format_adjust_value(self, field_name: str, value: float, decimals: int) -> str:
        text = f"{value:.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        if text == "-0":
            text = "0"

        if field_name == "zoom":
            return f"{text}x"
        return text

    def _build_preview_panel(self) -> QWidget:
        panel, layout = self._make_panel("Preview")

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addStretch(1)

        self.preview_window_button = QPushButton("Open in window")
        self.preview_window_button.clicked.connect(self.toggle_detached_preview)
        self._set_tooltip(self.preview_window_button, "Open the current fisheye preview in a separate window.")
        header.addWidget(self.preview_window_button)
        layout.addLayout(header)

        preview_frame = QFrame()
        preview_frame.setMinimumHeight(360)
        preview_frame.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #121518, stop:1 #1e242b);"
            "border-radius: 12px; border: 1px solid #2b333b;"
        )
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(18, 18, 18, 18)

        self.preview_label = PreviewCanvas()
        self.preview_label.clear_preview(self._preview_placeholder_text())
        self._set_tooltip(
            self.preview_label,
            "Fisheye preview canvas. Drag directly on the image to adjust the current correction. Wheel zooms the preview view.",
        )
        self.preview_label.drag_delta.connect(self.on_preview_drag)
        self.preview_label.zoom_delta.connect(self.on_preview_zoom)
        self.preview_label.reset_requested.connect(self.reset_preview_adjustments)
        self.preview_label.viewport_resized.connect(self.schedule_preview_resize_update)
        preview_layout.addWidget(self.preview_label, 1)

        layout.addWidget(preview_frame, 1)
        return panel

    def _build_preview_info_panel(self) -> QWidget:
        panel, layout = self._make_panel("Preview info")
        self.metrics_text = QTextEdit()
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setMinimumHeight(180)
        self.metrics_text.setPlainText("No preview rendered yet.")
        layout.addWidget(self.metrics_text, 1)
        return panel

    def _build_export_panel(self) -> QWidget:
        panel, layout = self._make_panel("Export")

        self.output_dir_edit = QLineEdit()
        self._set_tooltip(
            self.output_dir_edit,
            "Folder where corrected fisheye exports will be written.",
        )
        output_browse_button = QPushButton("Browse")
        output_browse_button.clicked.connect(self.choose_output_directory)
        self._set_tooltip(output_browse_button, "Choose the export folder for corrected images.")

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(output_browse_button)

        self.format_combo = QComboBox()
        self.format_combo.addItems(["preserve-raster", "linear-dng", "tiff", "jpeg"])
        self.format_combo.currentTextChanged.connect(self._update_export_summary)
        self._set_tooltip(
            self.format_combo,
            "Export policy. Preserve raster keeps raster formats when possible; RAW currently falls back to TIFF in this build.",
        )

        self.quality_spin = QDoubleSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setDecimals(0)
        self.quality_spin.setValue(95)
        self.quality_spin.valueChanged.connect(self._update_export_summary)
        self._set_tooltip(
            self.quality_spin,
            "JPEG quality used when exporting JPEG files. Higher values keep more detail but create larger files.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        output_folder_label = QLabel("Output folder")
        self._set_label_and_control_tooltip(
            output_folder_label,
            self.output_dir_edit,
            "Folder where corrected fisheye exports will be written.",
        )
        grid.addWidget(output_folder_label, 0, 0)
        grid.addLayout(output_row, 0, 1)
        format_policy_label = QLabel("Format policy")
        self._set_label_and_control_tooltip(
            format_policy_label,
            self.format_combo,
            "Export policy. Preserve raster keeps raster formats when possible; RAW currently falls back to TIFF in this build.",
        )
        grid.addWidget(format_policy_label, 1, 0)
        grid.addWidget(self.format_combo, 1, 1)
        jpeg_quality_label = QLabel("JPEG quality")
        self._set_label_and_control_tooltip(
            jpeg_quality_label,
            self.quality_spin,
            "JPEG quality used when exporting JPEG files. Higher values keep more detail but create larger files.",
        )
        grid.addWidget(jpeg_quality_label, 2, 0)
        grid.addWidget(self.quality_spin, 2, 1)
        layout.addLayout(grid)

        self.export_summary = QTextEdit()
        self.export_summary.setReadOnly(True)
        self.export_summary.setMinimumHeight(180)
        layout.addWidget(self.export_summary, 1)

        export_buttons = QHBoxLayout()
        export_buttons.setSpacing(10)

        self.export_selected_button = QPushButton("Export selected")
        self.export_selected_button.clicked.connect(self.run_export_selected)
        self.export_button = QPushButton("Queue batch export")
        self.export_button.clicked.connect(self.run_export_batch)
        self._set_tooltip(self.export_selected_button, "Export only the currently selected corrected image.")
        self._set_tooltip(self.export_button, "Export all listed source images using the current correction preset.")

        export_buttons.addWidget(self.export_selected_button)
        export_buttons.addWidget(self.export_button)
        layout.addLayout(export_buttons)
        return panel

    def _setup_preview_worker(self) -> None:
        self.preview_render_thread = QThread(self)
        self.preview_render_worker = PreviewWorker()
        self.preview_render_worker.moveToThread(self.preview_render_thread)
        self.preview_render_requested.connect(self.preview_render_worker.render)
        self.preview_render_worker.finished.connect(self.on_preview_render_finished)
        self.preview_render_worker.failed.connect(self.on_preview_render_failed)
        self.preview_render_thread.start()

    def _shutdown_preview_worker(self) -> None:
        if self.preview_render_thread is None:
            return
        self.preview_render_thread.quit()
        self.preview_render_thread.wait(1500)
        if self.preview_render_worker is not None:
            self.preview_render_worker.deleteLater()
        self.preview_render_thread.deleteLater()
        self.preview_render_worker = None
        self.preview_render_thread = None

    def _setup_panorama_worker(self) -> None:
        self.panorama_render_thread = QThread(self)
        self.panorama_render_worker = PanoramaWorker()
        self.panorama_render_worker.moveToThread(self.panorama_render_thread)
        self.panorama_render_requested.connect(self.panorama_render_worker.render)
        self.panorama_render_worker.progress.connect(self.on_panorama_render_progress)
        self.panorama_render_worker.finished.connect(self.on_panorama_render_finished)
        self.panorama_render_worker.failed.connect(self.on_panorama_render_failed)
        self.panorama_render_thread.start()

    def _shutdown_panorama_worker(self) -> None:
        if self.panorama_render_thread is None:
            return
        self.panorama_render_thread.quit()
        self.panorama_render_thread.wait(1500)
        if self.panorama_render_worker is not None:
            self.panorama_render_worker.deleteLater()
        self.panorama_render_thread.deleteLater()
        self.panorama_render_worker = None
        self.panorama_render_thread = None
        self.panorama_progress_dialog = None

    def _active_preview_canvas(self) -> PreviewCanvas:
        if self.detached_preview_window is not None:
            return self.detached_preview_window.preview_canvas
        return self.preview_label

    def _preview_placeholder_text(self) -> str:
        return (
            "Preview canvas\n\n"
            "Load a folder and choose a fisheye image.\n"
            "Wheel zooms the preview view inside the frame.\n\n"
            f"{self.interaction_hint}"
        )

    def on_step_selected(self, step_id: int) -> None:
        if step_id <= 0:
            return
        index = min(step_id - 1, self.workspace_stack.count() - 1)
        self.workspace_stack.setCurrentIndex(index)

    def _build_preview_output_frame(self, preset: CorrectionPreset) -> tuple[CorrectionPreset, FrameGeometry]:
        canvas = self._active_preview_canvas()
        target_width = max(960, int(round(canvas.width() * max(canvas.devicePixelRatioF(), 1.0) * 1.35)))
        target_height = max(540, int(round(canvas.height() * max(canvas.devicePixelRatioF(), 1.0) * 1.35)))
        output_frame = scaled_frame_to_bounds(preset.output_frame, target_width, target_height)
        return replace(preset, output_frame=output_frame), output_frame

    def choose_source_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose source folder", self.source_dir_edit.text() or str(Path.home()))
        if directory:
            self.source_dir_edit.setText(directory)
            self.load_source_directory()

    def choose_output_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_dir_edit.text() or str(Path.home()))
        if directory:
            self.output_dir_edit.setText(directory)

    def load_source_directory(self) -> None:
        directory = Path(self.source_dir_edit.text().strip()).expanduser()
        if not directory.exists() or not directory.is_dir():
            QMessageBox.warning(self, "Folder not found", "Choose an existing image folder first.")
            return

        self.image_assets = scan_directory_assets(directory)
        self.image_list.clear()
        self.loaded_preview_cache.clear()
        self.current_loaded_image = None
        self.current_rendered_image = None
        self.preview_request_serial += 1
        self.pending_preview_request = None
        self._populate_import_metadata_from_first_asset()

        for asset in self.image_assets:
            self.image_list.addItem(asset.path.name)

        if self.image_assets:
            suggested_output_dir = directory / "export"
            self.output_dir_edit.setText(str(suggested_output_dir))
            self.image_list.setCurrentRow(0)
            self.statusBar().showMessage(f"Loaded {len(self.image_assets)} images from {directory}.")
        else:
            self.camera_name_edit.clear()
            self.lens_name_edit.clear()
            self._clear_preview_views("No supported images found in the selected folder.")
            self.metrics_text.setPlainText("Supported formats: ARW, DNG, JPEG, TIFF, PNG, WebP, BMP.")
            self.statusBar().showMessage("No supported images found in the selected folder.")

    def on_image_selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self.image_assets):
            return

        asset = self.image_assets[row]
        try:
            loaded = self.loaded_preview_cache.get(asset.path)
            if loaded is None:
                loaded = load_image(asset.path, max_edge=self.preview_source_max_edge)
                self.loaded_preview_cache[asset.path] = loaded
            self.current_loaded_image = loaded
            self.preview_label.reset_view_zoom()
            if self.detached_preview_window is not None:
                self.detached_preview_window.preview_canvas.reset_view_zoom()
        except Exception as exc:
            QMessageBox.critical(self, "Image load failed", f"Could not load {asset.path.name}.\n\n{exc}")
            self.statusBar().showMessage(f"Failed to load {asset.path.name}.")
            return

        self.statusBar().showMessage(f"Loaded preview for {asset.path.name}.")
        self.schedule_preview_update()

    def _populate_import_metadata_from_first_asset(self) -> None:
        if not self.image_assets:
            self.base_preset = self.default_preset
            self._apply_preset_to_controls(self.base_preset)
            self.camera_name_edit.clear()
            self.lens_name_edit.clear()
            return

        first_asset = read_image_asset_metadata(self.image_assets[0].path)
        self.image_assets[0] = first_asset
        match = find_lens_database_match(first_asset.camera_model, first_asset.lens_model)
        self.base_preset = build_seed_preset_from_match(self.default_preset, match)
        self._apply_preset_to_controls(self.base_preset)
        self.camera_name_edit.setText(first_asset.camera_model or "")
        self.lens_name_edit.setText(first_asset.lens_model or "")

    def current_preset(self) -> CorrectionPreset:
        return replace(
            self.base_preset,
            name=self.preset_name_edit.text().strip() or self.base_preset.name,
            camera=replace(
                self.base_preset.camera,
                model=self.camera_name_edit.text().strip() or self.base_preset.camera.model,
            ),
            lens=replace(
                self.base_preset.lens,
                model=self.lens_name_edit.text().strip() or self.base_preset.lens.model,
                fisheye_mapping=self.mapping_combo.currentText(),
                diagonal_fov_deg=float(self.adjust_controls["lens_diagonal_fov_deg"].value()),
            ),
            output_projection=self.projection_combo.currentText(),
            horizontal_fov_deg=float(self.adjust_controls["horizontal_fov_deg"].value()),
            yaw_deg=float(self.adjust_controls["yaw_deg"].value()),
            pitch_deg=float(self.adjust_controls["pitch_deg"].value()),
            roll_deg=float(self.adjust_controls["roll_deg"].value()),
            zoom=float(self.adjust_controls["zoom"].value()),
            vertical_shift=float(self.adjust_controls["vertical_shift"].value()),
            post_rotate_deg=float(self.adjust_controls["post_rotate_deg"].value()),
            curve_straighten=0.0,
            curve_anchor_y=self.base_preset.curve_anchor_y,
            curve_span=self.base_preset.curve_span,
            safe_margin=float(self.adjust_controls["safe_margin"].value()),
            notes=self.notes_edit.toPlainText().strip(),
        )

    def current_export_options(self) -> ExportOptions:
        return ExportOptions(
            mode=self.format_combo.currentText(),
            suffix="_corrected",
            jpeg_quality=int(self.quality_spin.value()),
            keep_metadata=False,
            overwrite=False,
        )

    def current_output_dir(self) -> Path | None:
        output_dir_text = self.output_dir_edit.text().strip()
        if not output_dir_text:
            return None
        return Path(output_dir_text).expanduser()

    def current_selected_asset(self) -> ImageAsset | None:
        row = self.image_list.currentRow()
        if row < 0 or row >= len(self.image_assets):
            return None
        return self.image_assets[row]

    def schedule_preview_update(self) -> None:
        self._update_export_summary()
        if self.current_loaded_image is not None:
            self.render_timer.start()

    def schedule_preview_resize_update(self) -> None:
        if self.current_loaded_image is not None:
            self.preview_resize_timer.start()

    def render_preview(self) -> None:
        if self.current_loaded_image is None:
            return

        preset, output_frame = self._build_preview_output_frame(self.current_preset())
        self.preview_request_serial += 1
        request = PreviewRenderRequest(
            request_id=self.preview_request_serial,
            image_path=self.current_loaded_image.path,
            source_rgb=self.current_loaded_image.rgb_data,
            source_width=self.current_loaded_image.width,
            source_height=self.current_loaded_image.height,
            preset=preset,
            output_frame=output_frame,
            backend_api=self.render_backend.api,
        )
        if self.preview_render_busy:
            self.pending_preview_request = request
            self.statusBar().showMessage(f"Updating preview for {self.current_loaded_image.path.name}...")
            return
        self._dispatch_preview_request(request)

    def _dispatch_preview_request(self, request: PreviewRenderRequest) -> None:
        if self.preview_render_worker is None:
            return
        self.preview_render_busy = True
        self.pending_preview_request = None
        self.preview_render_requested.emit(request)

    def on_preview_render_finished(self, result: dict) -> None:
        self.preview_render_busy = False
        next_request = self.pending_preview_request
        self.pending_preview_request = None

        if (
            self.current_loaded_image is not None
            and result["request_id"] == self.preview_request_serial
            and result["image_path"] == self.current_loaded_image.path
        ):
            rendered = result["rendered"]
            metrics = result["metrics"]
            preset = result["preset"]
            selected = self.current_selected_asset()
            original_size_line = ""
            if selected is not None and selected.width and selected.height:
                original_size_line = f"Original size: {selected.width}x{selected.height}\n"
            self.current_rendered_image = rendered
            pixmap = self._pixmap_from_rgb(rendered)
            self.current_metrics_text = (
                f"Source: {result['image_path'].name}\n"
                f"{original_size_line}"
                f"Preview source size: {result['source_width']}x{result['source_height']}\n"
                f"Coverage estimate: {metrics['valid_fraction']:.2f}\n"
                f"Projection: {preset.output_projection} | Mapping: {preset.lens.fisheye_mapping}\n"
                f"Pitch: {preset.pitch_deg:.1f} | Roll: {preset.roll_deg:.1f} | Yaw: {preset.yaw_deg:.1f}\n"
                f"Rotate: {preset.post_rotate_deg:.1f} | Lens FOV: {preset.lens.diagonal_fov_deg:.1f}\n"
                f"Preview output: {int(metrics['output_width'])}x{int(metrics['output_height'])}\n"
                f"Backend: {self.render_backend.name} | {self.render_backend.detail}\n"
                f"{self.interaction_hint}"
            )
            self._update_preview_views(pixmap, self.current_metrics_text)
            self.statusBar().showMessage(f"Rendered preview for {result['image_path'].name}.")

        if next_request is not None:
            self._dispatch_preview_request(next_request)

    def on_preview_render_failed(self, request_id: int, message: str) -> None:
        self.preview_render_busy = False
        next_request = self.pending_preview_request
        self.pending_preview_request = None

        if request_id == self.preview_request_serial:
            QMessageBox.critical(self, "Preview failed", f"Could not render preview.\n\n{message}")
            self.statusBar().showMessage("Preview render failed.")

        if next_request is not None:
            self._dispatch_preview_request(next_request)

    def choose_panorama_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose panorama source folder",
            self.panorama_source_dir_edit.text() or self.source_dir_edit.text() or str(Path.home()),
        )
        if directory:
            self.panorama_source_dir_edit.setText(directory)
            self.load_panorama_directory()

    def choose_panorama_output_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose panorama output folder",
            self.panorama_output_dir_edit.text() or str(Path.home()),
        )
        if directory:
            self.panorama_output_dir_edit.setText(directory)

    def use_current_fisheye_folder_for_panorama(self) -> None:
        if self.source_dir_edit.text().strip():
            self.panorama_source_dir_edit.setText(self.source_dir_edit.text().strip())
            self.load_panorama_directory()

    def load_panorama_directory(self) -> None:
        directory = Path(self.panorama_source_dir_edit.text().strip()).expanduser()
        if not directory.exists() or not directory.is_dir():
            QMessageBox.warning(self, "Folder not found", "Choose an existing panorama folder first.")
            return

        self.panorama_assets = scan_directory_assets(directory)
        self.panorama_image_list.clear()
        self.current_panorama_image = None
        self.current_panorama_base_image = None
        self.current_panorama_base_metrics = None
        self.current_panorama_input_names = []
        self.current_panorama_used_precorrection = False
        self.current_panorama_metrics_text = "No panorama preview rendered yet."
        self.panorama_export_button.setEnabled(False)
        self._apply_panorama_preset_to_controls(self.panorama_default_preset)
        self.panorama_preview_label.clear_preview(
            "Panorama preview\n\n"
            "Select overlapping images and build a stitch preview."
        )

        for asset in self.panorama_assets:
            self.panorama_image_list.addItem(asset.path.name)

        self.select_all_panorama_images()
        self.panorama_output_dir_edit.setText(str(directory / "panorama-export"))
        self._update_panorama_export_summary()
        self.statusBar().showMessage(f"Loaded {len(self.panorama_assets)} panorama candidates from {directory}.")

    def select_all_panorama_images(self) -> None:
        self.panorama_image_list.selectAll()
        self._update_panorama_export_summary()

    def current_panorama_selected_paths(self) -> list[Path]:
        selected_names = {item.text() for item in self.panorama_image_list.selectedItems()}
        return [asset.path for asset in self.panorama_assets if asset.path.name in selected_names]

    def current_panorama_settings(self) -> PanoramaStitchSettings:
        return PanoramaStitchSettings(
            mode=self.panorama_mode_combo.currentText(),
            max_input_edge=int(self.panorama_max_edge_spin.value()),
            registration_resol_mpx=float(self.panorama_registration_spin.value()),
            seam_resol_mpx=float(self.panorama_seam_spin.value()),
            compositing_resol_mpx=float(self.panorama_compose_spin.value()),
            confidence_threshold=float(self.panorama_confidence_spin.value()),
            wave_correction=bool(self.panorama_wave_checkbox.isChecked()),
        )

    def _clear_panorama_preview_cache(self) -> None:
        clear_panorama_preview_cache()

    def _current_panorama_cache_key(self) -> str | None:
        image_paths = self.current_panorama_selected_paths()
        if len(image_paths) < 2:
            return None
        return build_panorama_cache_key(
            image_paths=image_paths,
            settings=self.current_panorama_settings(),
            use_fisheye_precorrection=bool(self.panorama_precorrect_checkbox.isChecked()),
            fisheye_preset=self.current_preset(),
        )

    def _restore_panorama_from_cache_entry(self, cache_entry) -> None:
        metadata = cache_entry.metadata
        self.current_panorama_base_image = cache_entry.rgb_data
        self.current_panorama_base_metrics = metadata.get("metrics", {})
        self.current_panorama_input_names = list(metadata.get("input_names", []))
        self.current_panorama_used_precorrection = bool(metadata.get("used_precorrection", False))
        self.render_current_panorama_adjustment()
        self._update_panorama_export_summary()

    def _maybe_restore_cached_panorama_preview(self, *_args) -> None:
        if self.panorama_render_busy:
            return
        cache_key = self._current_panorama_cache_key()
        if not cache_key:
            return
        cache_entry = load_panorama_preview_cache(cache_key)
        if cache_entry is None:
            return
        self._restore_panorama_from_cache_entry(cache_entry)
        self.statusBar().showMessage("Loaded panorama preview from session cache.")

    def current_panorama_preset(self) -> CorrectionPreset:
        return replace(
            self.panorama_default_preset,
            yaw_deg=float(self.panorama_adjust_controls["yaw_deg"].value()),
            pitch_deg=float(self.panorama_adjust_controls["pitch_deg"].value()),
            roll_deg=float(self.panorama_adjust_controls["roll_deg"].value()),
            zoom=float(self.panorama_adjust_controls["zoom"].value()),
            vertical_shift=float(self.panorama_adjust_controls["vertical_shift"].value()),
            post_rotate_deg=float(self.panorama_adjust_controls["post_rotate_deg"].value()),
            horizontal_fov_deg=float(self.panorama_adjust_controls["horizontal_fov_deg"].value()),
            safe_margin=float(self.panorama_adjust_controls["safe_margin"].value()),
        )

    def _set_panorama_control_value(self, field_name: str, value: float) -> None:
        widget = self.panorama_adjust_controls[field_name]
        bounded = max(widget.minimum(), min(widget.maximum(), value))
        widget.setValue(bounded)

    def _apply_panorama_preset_to_controls(self, preset: CorrectionPreset) -> None:
        for field_name, value in {
            "pitch_deg": preset.pitch_deg,
            "roll_deg": preset.roll_deg,
            "yaw_deg": preset.yaw_deg,
            "post_rotate_deg": preset.post_rotate_deg,
            "zoom": preset.zoom,
            "vertical_shift": preset.vertical_shift,
            "horizontal_fov_deg": preset.horizontal_fov_deg,
            "safe_margin": preset.safe_margin,
        }.items():
            widget = self.panorama_adjust_controls[field_name]
            with QSignalBlocker(widget):
                widget.setValue(value)
            if field_name in self.panorama_adjust_value_labels:
                decimals = widget.decimals()
                self.panorama_adjust_value_labels[field_name].setText(self._format_adjust_value(field_name, value, decimals))

    def schedule_panorama_adjustment(self) -> None:
        if self.current_panorama_base_image is None:
            self._update_panorama_export_summary()
            return
        self.panorama_adjust_timer.start()

    def _build_panorama_output_frame(self) -> FrameGeometry:
        if self.current_panorama_base_image is None:
            return FrameGeometry(width=960, height=540)
        source_frame = FrameGeometry(
            width=int(self.current_panorama_base_image.shape[1]),
            height=int(self.current_panorama_base_image.shape[0]),
        )
        max_width = max(640, self.panorama_preview_label.width())
        max_height = max(360, self.panorama_preview_label.height())
        return scaled_frame_to_bounds(source_frame, max_width, max_height)

    def render_current_panorama_adjustment(self) -> None:
        if self.current_panorama_base_image is None:
            return

        preset = self.current_panorama_preset()
        output_frame = self._build_panorama_output_frame()
        rendered, metrics = render_panorama_adjusted_rgb(
            self.current_panorama_base_image,
            preset,
            output_frame=output_frame,
            backend_api=self.render_backend.api,
        )
        self.current_panorama_image = rendered
        self.panorama_preview_label.set_preview_pixmap(self._pixmap_from_rgb(rendered))
        self._update_panorama_metrics_text(metrics)
        self._update_panorama_export_summary()

    def reset_panorama_preview_adjustments(self) -> None:
        self._apply_panorama_preset_to_controls(self.panorama_default_preset)
        self.schedule_panorama_adjustment()
        self.statusBar().showMessage("Panorama preview adjustments reset.")

    def on_panorama_preview_drag(self, dx: float, dy: float, anchor_x: float, anchor_y: float, button: int, modifiers: int) -> None:
        if self.current_panorama_base_image is None:
            return

        is_shift = bool(modifiers & enum_value(Qt.KeyboardModifier.ShiftModifier))
        is_alt = bool(modifiers & enum_value(Qt.KeyboardModifier.AltModifier))
        is_right_drag = button == enum_value(Qt.MouseButton.RightButton)
        edge_weight = min(1.0, abs(anchor_y))

        if is_alt:
            self._set_panorama_control_value(
                "safe_margin",
                self.panorama_adjust_controls["safe_margin"].value() + (dy * 0.0015),
            )
            self.statusBar().showMessage("Panorama drag: adjusting crop margin.")
            return

        if is_right_drag or is_shift:
            self._set_panorama_control_value("roll_deg", self.panorama_adjust_controls["roll_deg"].value() + (dx * 0.18))
            self._set_panorama_control_value(
                "post_rotate_deg",
                self.panorama_adjust_controls["post_rotate_deg"].value() + (dx * 0.14),
            )
            self._set_panorama_control_value(
                "vertical_shift",
                self.panorama_adjust_controls["vertical_shift"].value() - (dy * (0.004 + 0.004 * edge_weight)),
            )
            self.statusBar().showMessage("Panorama drag: rotating image and adjusting vertical offset.")
            return

        if button == enum_value(Qt.MouseButton.MiddleButton):
            self._set_panorama_control_value(
                "vertical_shift",
                self.panorama_adjust_controls["vertical_shift"].value() - (dy * 0.008),
            )
            self.statusBar().showMessage("Panorama drag: shifting the image vertically.")
            return

        self._set_panorama_control_value("yaw_deg", self.panorama_adjust_controls["yaw_deg"].value() + (dx * 0.08))
        self._set_panorama_control_value("pitch_deg", self.panorama_adjust_controls["pitch_deg"].value() - (dy * (0.10 + 0.06 * edge_weight)))
        self._set_panorama_control_value(
            "vertical_shift",
            self.panorama_adjust_controls["vertical_shift"].value() - (dy * (0.003 + 0.004 * edge_weight)),
        )
        self.statusBar().showMessage("Panorama drag: adjusting the current correction.")

    def on_panorama_preview_zoom(self, steps: float, anchor_x: float, anchor_y: float, modifiers: int) -> None:
        if self.current_panorama_base_image is None:
            return

        if modifiers & enum_value(Qt.KeyboardModifier.ControlModifier):
            self._set_panorama_control_value("zoom", self.panorama_adjust_controls["zoom"].value() + (steps * 0.05))
            self.statusBar().showMessage("Panorama wheel: adjusting correction zoom.")
            return

        if modifiers & enum_value(Qt.KeyboardModifier.ShiftModifier):
            self._set_panorama_control_value(
                "horizontal_fov_deg",
                self.panorama_adjust_controls["horizontal_fov_deg"].value() + (steps * 1.5),
            )
            self.statusBar().showMessage("Panorama wheel: adjusting horizontal field of view.")
            return

        if modifiers & enum_value(Qt.KeyboardModifier.AltModifier):
            self._set_panorama_control_value(
                "safe_margin",
                self.panorama_adjust_controls["safe_margin"].value() + (steps * 0.01),
            )
            self.statusBar().showMessage("Panorama wheel: adjusting crop margin.")
            return

    def _update_panorama_metrics_text(self, adjust_metrics: dict | None = None) -> None:
        preset = self.current_panorama_preset()
        lines: list[str] = []
        if self.current_panorama_base_metrics is not None:
            lines.extend(
                [
                    f"Images stitched: {self.current_panorama_base_metrics['image_count']}",
                    f"Mode: {self.current_panorama_base_metrics['mode']}",
                    f"Stitch output: {self.current_panorama_base_metrics['output_width']}x{self.current_panorama_base_metrics['output_height']}",
                ]
            )
        lines.extend(
            [
                f"Fisheye precorrection: {'on' if self.current_panorama_used_precorrection else 'off'}",
                f"Backend: {self.render_backend.name}",
                f"Pitch: {preset.pitch_deg:.1f} | Roll: {preset.roll_deg:.1f} | Yaw: {preset.yaw_deg:.1f}",
                f"Rotate: {preset.post_rotate_deg:.1f} | Zoom: {preset.zoom:.2f}x",
                f"Vertical shift: {preset.vertical_shift:.3f} | Horizontal FOV: {preset.horizontal_fov_deg:.1f}",
                f"Crop margin: {preset.safe_margin:.3f}",
            ]
        )
        if adjust_metrics is not None:
            lines.append(
                f"Preview output: {int(adjust_metrics['output_width'])}x{int(adjust_metrics['output_height'])} | Coverage: {adjust_metrics['valid_fraction']:.2f}"
            )
        if self.current_panorama_input_names:
            lines.append("Inputs:")
            lines.extend(f"- {name}" for name in self.current_panorama_input_names)
        self.current_panorama_metrics_text = "\n".join(lines)
        self.panorama_metrics_text.setPlainText(self.current_panorama_metrics_text)

    def run_panorama_preview(self) -> None:
        image_paths = self.current_panorama_selected_paths()
        if len(image_paths) < 2:
            QMessageBox.information(self, "Need more images", "Select at least two overlapping images to build a panorama preview.")
            return
        if self.panorama_render_busy:
            QMessageBox.information(self, "Panorama busy", "Wait for the current panorama preview to finish first.")
            return
        if self.panorama_render_worker is None:
            QMessageBox.critical(self, "Panorama unavailable", "Panorama worker is not available.")
            return

        cache_key = self._current_panorama_cache_key()
        if cache_key is not None:
            cache_entry = load_panorama_preview_cache(cache_key)
            if cache_entry is not None:
                self._restore_panorama_from_cache_entry(cache_entry)
                self.panorama_export_button.setEnabled(True)
                self.panorama_metrics_text.setPlainText(self.current_panorama_metrics_text)
                self.statusBar().showMessage("Loaded panorama preview from session cache.")
                return

        self.panorama_request_serial += 1
        total_steps = len(image_paths) + 1
        request = PanoramaRenderRequest(
            request_id=self.panorama_request_serial,
            cache_key=cache_key or "",
            image_paths=image_paths,
            settings=self.current_panorama_settings(),
            use_fisheye_precorrection=bool(self.panorama_precorrect_checkbox.isChecked()),
            fisheye_preset=self.current_preset(),
            backend_api=self.render_backend.api,
        )
        self.panorama_render_busy = True
        self.panorama_build_button.setEnabled(False)
        self.panorama_export_button.setEnabled(False)
        self.current_panorama_image = None
        self.current_panorama_base_image = None
        self.panorama_metrics_text.setPlainText("Building panorama preview...")
        self.panorama_progress_dialog = PanoramaProgressDialog(self)
        self.panorama_progress_dialog.start(total_steps)
        self.panorama_progress_dialog.update_progress(0, total_steps, "Preparing panorama build...")
        self.statusBar().showMessage(f"Building panorama preview from {len(image_paths)} images.")
        self.panorama_render_requested.emit(request)
        self.panorama_progress_dialog.show()

    def on_panorama_render_progress(self, request_id: int, completed: int, total: int, message: str) -> None:
        if request_id != self.panorama_request_serial:
            return
        if self.panorama_progress_dialog is not None:
            self.panorama_progress_dialog.update_progress(completed, total, message)
        self.statusBar().showMessage(message)

    def on_panorama_render_finished(self, result: dict) -> None:
        self.panorama_render_busy = False
        self.panorama_build_button.setEnabled(True)
        self.panorama_export_button.setEnabled(True)
        if self.panorama_progress_dialog is not None:
            self.panorama_progress_dialog.close()
            self.panorama_progress_dialog = None

        if result["request_id"] != self.panorama_request_serial:
            return

        self.current_panorama_base_image = result["rendered"]
        self.current_panorama_base_metrics = result["metrics"]
        self.current_panorama_input_names = list(result["input_names"])
        self.current_panorama_used_precorrection = bool(result["used_precorrection"])
        if result.get("cache_key"):
            save_panorama_preview_cache(
                result["cache_key"],
                self.current_panorama_base_image,
                {
                    "metrics": self.current_panorama_base_metrics,
                    "input_names": self.current_panorama_input_names,
                    "used_precorrection": self.current_panorama_used_precorrection,
                    "backend_api": result.get("backend_api", self.render_backend.api),
                    "max_input_edge": result.get("max_input_edge"),
                },
            )
        self.render_current_panorama_adjustment()
        self._update_panorama_export_summary()
        self.statusBar().showMessage("Panorama preview built.")

    def on_panorama_render_failed(self, request_id: int, message: str) -> None:
        self.panorama_render_busy = False
        self.panorama_build_button.setEnabled(True)
        self.panorama_export_button.setEnabled(self.current_panorama_image is not None)
        if self.panorama_progress_dialog is not None:
            self.panorama_progress_dialog.close()
            self.panorama_progress_dialog = None
        if request_id != self.panorama_request_serial:
            return
        self.current_panorama_base_image = None
        self.current_panorama_base_metrics = None
        QMessageBox.critical(self, "Panorama stitch failed", message)
        self.panorama_metrics_text.setPlainText(message)
        self.statusBar().showMessage("Panorama stitch failed.")

    def _update_panorama_export_summary(self) -> None:
        selected_paths = self.current_panorama_selected_paths() if hasattr(self, "panorama_image_list") else []
        lines = [
            f"Selected images: {len(selected_paths)}",
            f"Mode: {self.panorama_mode_combo.currentText() if hasattr(self, 'panorama_mode_combo') else 'panorama'}",
            (
                "Pre-correct fisheye with active preset before stitching."
                if hasattr(self, "panorama_precorrect_checkbox") and self.panorama_precorrect_checkbox.isChecked()
                else "Stitch original loaded images directly."
            ),
            f"Preview max input edge: {self.panorama_max_edge_spin.value() if hasattr(self, 'panorama_max_edge_spin') else 1800}px",
            f"Backend: {self.render_backend.name}",
            f"Panorama ready: {'yes' if self.current_panorama_image is not None else 'no'}",
        ]
        if self.panorama_adjust_controls:
            lines.extend(
                [
                    f"Panorama pitch: {self.panorama_adjust_controls['pitch_deg'].value():.1f}",
                    f"Panorama yaw: {self.panorama_adjust_controls['yaw_deg'].value():.1f}",
                    f"Panorama zoom: {self.panorama_adjust_controls['zoom'].value():.2f}x",
                ]
            )
        if hasattr(self, "panorama_export_summary"):
            self.panorama_export_summary.setPlainText("\n".join(lines))

    def export_current_panorama(self) -> None:
        if self.current_panorama_image is None:
            QMessageBox.information(self, "No panorama preview", "Build a panorama preview first.")
            return

        output_dir_text = self.panorama_output_dir_edit.text().strip()
        if not output_dir_text:
            QMessageBox.warning(self, "Missing output folder", "Choose an output folder for the panorama first.")
            return

        output_dir = Path(output_dir_text).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_format = self.panorama_format_combo.currentText()
        base_name = Path(self.panorama_source_dir_edit.text().strip()).name or "panorama"
        output_path = output_dir / f"{base_name}_stitched.{output_format}"
        suffix_index = 2
        while output_path.exists():
            output_path = output_dir / f"{base_name}_stitched_{suffix_index}.{output_format}"
            suffix_index += 1

        save_rgb_image(self.current_panorama_image, output_path, output_format, jpeg_quality=95)
        self.statusBar().showMessage(f"Exported panorama to {output_path}.")
        QMessageBox.information(self, "Panorama exported", f"Saved panorama preview to:\n{output_path}")

    def run_export_batch(self) -> None:
        if not self.image_assets:
            QMessageBox.information(self, "Nothing to export", "Load a folder with images first.")
            return
        self._start_export([asset.path for asset in self.image_assets], "batch")

    def run_export_selected(self) -> None:
        asset = self.current_selected_asset()
        if asset is None:
            QMessageBox.information(self, "No image selected", "Choose a current image first.")
            return
        self._start_export([asset.path], "selected image")

    def _start_export(self, image_paths: list[Path], scope_label: str) -> None:
        if self.export_thread is not None:
            QMessageBox.information(self, "Export already running", "Wait for the current export to finish first.")
            return

        output_dir = self.current_output_dir()
        if output_dir is None:
            QMessageBox.warning(self, "Missing output folder", "Choose an output folder first.")
            return

        preset = self.current_preset()
        export_options = self.current_export_options()

        self.pending_export_scope = scope_label
        self.pending_export_output_dir = output_dir
        self.export_dialog = ExportProgressDialog(self)
        self.export_dialog.set_export_scope(scope_label, len(image_paths))
        self.export_dialog.update_progress(0, len(image_paths), "Preparing export...")

        self.export_thread = QThread(self)
        self.export_worker = ExportWorker(image_paths, preset, output_dir, export_options, self.render_backend.api)
        self.export_worker.moveToThread(self.export_thread)

        self.export_thread.started.connect(self.export_worker.run)
        self.export_worker.progress.connect(self.on_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.failed.connect(self.on_export_failed)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.failed.connect(self.export_thread.quit)
        self.export_thread.finished.connect(self._cleanup_export_thread)

        self.export_button.setEnabled(False)
        self.export_selected_button.setEnabled(False)
        self.statusBar().showMessage(f"Started export of {scope_label}.")

        self.export_thread.start()
        self.export_dialog.show()

    def on_export_progress(self, completed: int, total: int, message: str) -> None:
        if self.export_dialog is not None:
            self.export_dialog.update_progress(completed, total, message)

    def on_export_finished(self, result: dict) -> None:
        if self.export_dialog is not None:
            self.export_dialog.close()

        self.export_button.setEnabled(True)
        self.export_selected_button.setEnabled(True)

        output_dir = self.pending_export_output_dir or Path(".")
        notes = "\n".join(result["notes"]) if result["notes"] else "Export completed with no extra notes."
        title = "Export complete" if self.pending_export_scope == "selected image" else "Batch export complete"
        QMessageBox.information(
            self,
            title,
            f"Exported {result['count']} image(s) to:\n{output_dir}\n\n{notes}",
        )
        self.statusBar().showMessage(f"Exported {result['count']} image(s) to {output_dir}.")

    def on_export_failed(self, error_type: str, message: str) -> None:
        if self.export_dialog is not None:
            self.export_dialog.close()

        self.export_button.setEnabled(True)
        self.export_selected_button.setEnabled(True)

        if error_type == "NotImplementedError":
            QMessageBox.information(self, "Export mode not ready", message)
            self.statusBar().showMessage("Selected export mode is not implemented yet.")
            return

        QMessageBox.critical(self, "Export failed", f"Could not export the files.\n\n{message}")
        self.statusBar().showMessage("Export failed.")

    def _cleanup_export_thread(self) -> None:
        if self.export_worker is not None:
            self.export_worker.deleteLater()
        if self.export_thread is not None:
            self.export_thread.deleteLater()
        self.export_worker = None
        self.export_thread = None
        self.export_dialog = None

    def _apply_preset_to_controls(self, preset: CorrectionPreset) -> None:
        with QSignalBlocker(self.projection_combo):
            self.projection_combo.setCurrentText(preset.output_projection)
        with QSignalBlocker(self.mapping_combo):
            self.mapping_combo.setCurrentText(preset.lens.fisheye_mapping)

        for field_name, value in {
            "pitch_deg": preset.pitch_deg,
            "roll_deg": preset.roll_deg,
            "yaw_deg": preset.yaw_deg,
            "post_rotate_deg": preset.post_rotate_deg,
            "zoom": preset.zoom,
            "vertical_shift": preset.vertical_shift,
            "horizontal_fov_deg": preset.horizontal_fov_deg,
            "lens_diagonal_fov_deg": preset.lens.diagonal_fov_deg,
            "safe_margin": preset.safe_margin,
        }.items():
            widget = self.adjust_controls[field_name]
            with QSignalBlocker(widget):
                widget.setValue(value)

        self.preset_name_edit.setText(preset.name)
        self.notes_edit.setPlainText(preset.notes)

    def _update_export_summary(self) -> None:
        preset = self.current_preset()
        mode = self.format_combo.currentText()
        selection = self.current_selected_asset()
        summary_lines = [
            f"Preset: {preset.name}",
            f"Projection: {preset.output_projection}",
            f"Rotate image: {preset.post_rotate_deg:.1f} deg",
            f"Preview mode: {self.render_backend.preview_mode}",
            f"Backend: {self.render_backend.name}",
            f"JPEG quality: {int(self.quality_spin.value())}",
            f"Selected image: {selection.path.name if selection else 'none'}",
        ]

        if mode == "preserve-raster":
            summary_lines.extend(
                [
                    "Raster inputs keep their original raster extension.",
                    "RAW and DNG inputs currently export as TIFF in this build.",
                    "Suffix: _corrected",
                ]
            )
        elif mode == "linear-dng":
            summary_lines.extend(
                [
                    "Linear DNG export is planned, but not implemented yet.",
                    "Choose TIFF or JPEG for a working export today.",
                ]
            )
        elif mode == "tiff":
            summary_lines.extend(["All selected images will export as TIFF.", "Suffix: _corrected"])
        elif mode == "jpeg":
            summary_lines.extend(["All selected images will export as JPEG.", "Suffix: _corrected"])

        self.export_summary.setPlainText("\n".join(summary_lines))

    def _pixmap_from_rgb(self, rgb_data) -> QPixmap:
        height, width, _channels = rgb_data.shape
        bytes_per_line = width * 3
        image = QImage(rgb_data.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image.copy())

    def _set_control_value(self, field_name: str, value: float) -> None:
        widget = self.adjust_controls[field_name]
        bounded = max(widget.minimum(), min(widget.maximum(), value))
        widget.setValue(bounded)

    def on_preview_drag(self, dx: float, dy: float, anchor_x: float, anchor_y: float, button: int, modifiers: int) -> None:
        if self.current_loaded_image is None:
            return

        is_shift = bool(modifiers & enum_value(Qt.KeyboardModifier.ShiftModifier))
        is_alt = bool(modifiers & enum_value(Qt.KeyboardModifier.AltModifier))
        is_right_drag = button == enum_value(Qt.MouseButton.RightButton)
        edge_weight = min(1.0, abs(anchor_y))
        center_weight = 1.0 - min(1.0, abs(anchor_x))
        side_weight = min(1.0, abs(anchor_x))

        if is_alt:
            self._set_control_value(
                "lens_diagonal_fov_deg",
                self.adjust_controls["lens_diagonal_fov_deg"].value() + (dy * 0.12 * max(edge_weight, 0.25)),
            )
            self._set_control_value("safe_margin", self.adjust_controls["safe_margin"].value() + (dy * 0.0015))
            self.statusBar().showMessage("Preview drag: adjusting lens diagonal FOV and crop margin.")
            return

        if is_right_drag or is_shift:
            self._set_control_value("roll_deg", self.adjust_controls["roll_deg"].value() + (dx * 0.18))
            self._set_control_value("post_rotate_deg", self.adjust_controls["post_rotate_deg"].value() + (dx * 0.14))
            self._set_control_value("vertical_shift", self.adjust_controls["vertical_shift"].value() - (dy * (0.004 + 0.004 * edge_weight)))
            self.statusBar().showMessage("Preview drag: rotating image and adjusting vertical offset.")
            return

        if button == enum_value(Qt.MouseButton.MiddleButton):
            self._set_control_value("vertical_shift", self.adjust_controls["vertical_shift"].value() - (dy * 0.008))
            self.statusBar().showMessage("Preview drag: shifting the image vertically.")
            return

        self._set_control_value("yaw_deg", self.adjust_controls["yaw_deg"].value() + (dx * (0.05 + 0.02 * (1.0 - edge_weight))))
        self._set_control_value("pitch_deg", self.adjust_controls["pitch_deg"].value() - (dy * (0.09 + 0.09 * edge_weight)))

        if edge_weight > 0.20:
            self._set_control_value("vertical_shift", self.adjust_controls["vertical_shift"].value() - (dy * (0.003 + 0.006 * edge_weight)))
            self._set_control_value(
                "lens_diagonal_fov_deg",
                self.adjust_controls["lens_diagonal_fov_deg"].value() + (dy * 0.12 * max(center_weight, 0.15)),
            )

        if side_weight > 0.45:
            self._set_control_value("roll_deg", self.adjust_controls["roll_deg"].value() + (dx * anchor_y * 0.08))

        self.statusBar().showMessage("Preview drag: adjusting the current geometry preset.")

    def on_preview_zoom(self, steps: float, anchor_x: float, anchor_y: float, modifiers: int) -> None:
        if self.current_loaded_image is None:
            return

        if modifiers & enum_value(Qt.KeyboardModifier.ControlModifier):
            self._set_control_value("zoom", self.adjust_controls["zoom"].value() + (steps * 0.05))
            self.statusBar().showMessage("Preview wheel: adjusting correction zoom.")
            return

        if modifiers & enum_value(Qt.KeyboardModifier.ShiftModifier):
            self._set_control_value("lens_diagonal_fov_deg", self.adjust_controls["lens_diagonal_fov_deg"].value() + (steps * 1.5))
            self.statusBar().showMessage("Preview wheel: adjusting lens diagonal field of view.")
            return

        if modifiers & enum_value(Qt.KeyboardModifier.AltModifier):
            self._set_control_value("safe_margin", self.adjust_controls["safe_margin"].value() + (steps * 0.01))
            self.statusBar().showMessage("Preview wheel: adjusting crop margin.")
            return

    def reset_preview_adjustments(self) -> None:
        self._apply_preset_to_controls(self.base_preset)
        self.schedule_preview_update()
        self.statusBar().showMessage("Preview adjustments reset to the Sigma start preset.")

    def toggle_detached_preview(self) -> None:
        if self.detached_preview_window is None:
            self.detached_preview_window = DetachedPreviewWindow()
            self.detached_preview_window.preview_canvas.drag_delta.connect(self.on_preview_drag)
            self.detached_preview_window.preview_canvas.zoom_delta.connect(self.on_preview_zoom)
            self.detached_preview_window.preview_canvas.reset_requested.connect(self.reset_preview_adjustments)
            self.detached_preview_window.preview_canvas.viewport_resized.connect(self.schedule_preview_resize_update)
            self.detached_preview_window.closed.connect(self.on_detached_preview_closed)
            self._sync_detached_preview_window()
            self.preview_label.setEnabled(False)
            self.preview_label.clear_preview("Preview moved to the separate window.")
            self.detached_preview_window.show()
            self.preview_window_button.setText("Focus window")
            self.schedule_preview_update()
            return

        self.detached_preview_window.show()
        self.detached_preview_window.raise_()
        self.detached_preview_window.activateWindow()

    def on_detached_preview_closed(self) -> None:
        self.detached_preview_window = None
        self.preview_window_button.setText("Open in window")
        self.preview_label.setEnabled(True)
        if self.current_rendered_image is not None:
            self.preview_label.set_preview_pixmap(self._pixmap_from_rgb(self.current_rendered_image))
        else:
            self.preview_label.clear_preview(self._preview_placeholder_text())
        self.schedule_preview_update()

    def _sync_detached_preview_window(self) -> None:
        if self.detached_preview_window is None:
            return
        self.detached_preview_window.metrics_text.setPlainText(self.current_metrics_text)
        if self.current_rendered_image is not None:
            self.detached_preview_window.preview_canvas.set_preview_pixmap(self._pixmap_from_rgb(self.current_rendered_image))
        else:
            self.detached_preview_window.preview_canvas.clear_preview(self._preview_placeholder_text())

    def _update_preview_views(self, pixmap: QPixmap, metrics_text: str) -> None:
        if self.detached_preview_window is None:
            self.preview_label.setEnabled(True)
            self.preview_label.set_preview_pixmap(pixmap)
        else:
            self.preview_label.setEnabled(False)
            self.preview_label.clear_preview("Preview moved to the separate window.")
        self.metrics_text.setPlainText(metrics_text)
        self._sync_detached_preview_window()

    def _clear_preview_views(self, message: str) -> None:
        if self.detached_preview_window is None:
            self.preview_label.setEnabled(True)
            self.preview_label.clear_preview(message)
        else:
            self.preview_label.setEnabled(False)
            self.preview_label.clear_preview("Preview moved to the separate window.")
        self.current_metrics_text = "No preview rendered yet."
        self._sync_detached_preview_window()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.current_loaded_image is not None:
            self.schedule_preview_resize_update()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._shutdown_preview_worker()
        self._shutdown_panorama_worker()
        super().closeEvent(event)
