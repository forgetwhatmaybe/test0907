import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtNetwork import QLocalSocket, QLocalServer
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    server_name = "LanHao_SingleInstance"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    
    if socket.waitForConnected(500):
        QMessageBox.warning(None, "提示","BU蓝昊_pic_video 已经在运行中！")
        sys.exit(0)
    
    server = QLocalServer()
    server.removeServer(server_name)
    if not server.listen(server_name):
        print(f"无法启动单实例服务器: {server.errorString()}")
    
    app.setStyleSheet("""
        QToolTip {
            background-color: #3d3d3d;
            color: white;
            border: 1px solid #555;
            padding: 5px;
        }
        QFileDialog {
            background-color: #2d2d2d;
        }
        QFileDialog QLabel {
            color: white;
        }
        QComboBox QAbstractItemView {
            background-color: #2d2d2d;
            color: white;
            selection-background-color: #4a4a4a;
        }
    """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
