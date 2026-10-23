from .qt import *
from .common import *
from .vpk_io import *
from .kv import *
from .models import *
from .database import *
from .applier import *
from .presets import *
from .icons import *
from .cleanup import *
from .bridge import *
from .steam import *

class ChameleonWindow(QMainWindow):
    db_loaded_signal = Signal(bool)
    status_signal = Signal(str)
    apply_result_signal = Signal(bool)
    launch_result_signal = Signal(bool)
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(1000, 640)
        self.resize(1200, 800)
        self.config = self.load_config()
        self.database = None; self.applier = None
        self.bridge = ChameleonBridge(); self.bridge.set_window(self)
        self.bridge.config = self.config
        IconManager._hub()                       # QObjects for icons must be created in the GUI thread
        IconManager.configure(self.config.get('icon_source', 'auto'), self.config.get('icon_fix_cast', True))
        self.bridge._connect_icons()
        self.setup_ui()
        self.db_loaded_signal.connect(self._on_db_loaded)
        self.db_loaded_signal.connect(self.bridge.dbLoaded)
        self.status_signal.connect(lambda msg: self.bridge.statusChanged.emit(msg))
        self.apply_result_signal.connect(self.bridge.applyResult)
        self.launch_result_signal.connect(self.bridge.launchResult)
        self.auto_detect_paths()
    def load_config(self):
        cfg = DEFAULT_CONFIG.copy()
        if CONFIG_FILE.exists():
            try: cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
            except Exception: pass
        return cfg
    def _on_db_loaded(self, ok):
        if ok and self.database:
            IconManager.set_vpk_readers(self.database.vpk_readers)
    def save_config(self):
        CONFIG_FILE.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
    def setup_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        central.setObjectName("centralWidget")
        central.setStyleSheet("#centralWidget { background: transparent; }")
        layout = QVBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        self.web_view = QWebEngineView()
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.web_channel = QWebChannel()
        self.web_channel.registerObject("chameleon", self.bridge)
        self.web_view.page().setWebChannel(self.web_channel)
        html = (Path(__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
        self.web_view.setHtml(html, QUrl("qrc:///"))
        layout.addWidget(self.web_view)
    def auto_detect_paths(self):
        steam_path = SteamDetector.detect_steam()
        if steam_path:
            self.config["steam_path"] = str(steam_path)
            dota_path = SteamDetector.detect_dota(steam_path)
            if dota_path:
                self.config["dota_path"] = str(dota_path)
                self.save_config(); self.load_database()
            else: self.status_signal.emit("Dota 2 not found")
        else: self.status_signal.emit("Steam not found")
    def load_database(self):
        self.status_signal.emit("Loading database...")
        def load_thread():
            success = False
            try:
                self.database = SkinDatabase(Path(self.config["dota_path"]))
                self.database.item_language = self.config.get("item_language", "english") or "english"
                success = self.database.initialize(progress_callback=lambda msg: self.status_signal.emit(msg))
                if success:
                    self.applier = SkinApplier(Path(self.config["dota_path"]), self.database, self.config)
                    self.bridge.set_database(self.database); self.bridge.set_applier(self.applier)
                    self.bridge.config = self.config
                    self.bridge.mark_db_ready()
            except Exception as e:
                log.error(f"Database load error: {e}"); self.status_signal.emit(f"Error: {e}")
            finally: self.db_loaded_signal.emit(success)
        threading.Thread(target=load_thread, daemon=True).start()
    def closeEvent(self, event):
        if self.config.get("auto_restore_on_exit", True) and self.applier: self.applier.restore()
        IconManager.stop_worker()
        self.save_config(); event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    window = ChameleonWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
