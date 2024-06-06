import os
from PyQt6.QtCore import Qt, QProcess
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QPushButton, QListWidget, QMessageBox, QInputDialog, QDialog, QLineEdit, QLabel, QFileDialog
from src.windows.tool_display import ToolDisplay
from src.windows.tool_launcher import ToolLauncher
from PyQt6.QtGui import QValidator
from src.windows.url_validator import URLValidator
import shutil
import pathlib
import subprocess

class OTWindow(QMainWindow):
    imported_dir = "src/windows/imported"
    SEQ_DIR = os.path.join(imported_dir, "seq")
    TOOLS_FILE = os.path.join(SEQ_DIR, "tools.txt")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.available_tools = QListWidget()
        self.initUI()
        self.ensure_directories()
        self.load_tools()
        self.tool_display = ToolDisplay()
        self.github_repo_url = QLineEdit()
        self.launch_command = QLineEdit()
        self.query = QLineEdit()
        self.parent_dir = QLineEdit()
        self.tool_launcher = ToolLauncher("src/windows/imported")
        self.imported_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'windows', 'imported')
        if not os.path.exists(self.imported_dir):
            os.makedirs(self.imported_dir)

    def initUI(self):
        self.setWindowTitle("Odinova Digital Tiger: Import Tools Window")
        self.setGeometry(100, 100, 800, 600)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Add widgets to layout
        self.add_placeholder_label(layout)
        self.github_url_input = self.add_line_edit(layout, "Enter GitHub repository URL")
        self.command_input = self.add_line_edit(layout, "Enter command to launch the tool")
        self.query_input = self.add_line_edit(layout, "Enter query (optional)")
        self.parent_dir_input = self.add_line_edit(layout, "Enter parent directory")
        self.add_button(layout, "Import Tool", self.import_tool)
        self.tool_list = QListWidget(self)
        layout.addWidget(self.tool_list)
        self.add_button(layout, "Launch Tool", self.launch_tool)
        self.add_button(layout, "Edit Launch Command", self.edit_command)
        self.add_button(layout, "Delete Tool", self.delete_tool)

    def add_placeholder_label(self, layout):
        placeholder_label = QLabel("Please make sure your run file is in your parent directory, else- example: 'python3 path/to/run_file.py'")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(placeholder_label)

    def add_line_edit(self, layout, placeholder_text):
        line_edit = QLineEdit(self)
        line_edit.setPlaceholderText(placeholder_text)
        layout.addWidget(line_edit)
        return line_edit

    def add_button(self, layout, text, callback):
        button = QPushButton(text, self)
        button.clicked.connect(callback)
        layout.addWidget(button)

    def ensure_directories(self):
        os.makedirs(self.imported_dir, exist_ok=True)
        os.makedirs(self.SEQ_DIR, exist_ok=True)
        # Create tools.txt if it doesn't exist
        if not os.path.exists(self.TOOLS_FILE):
            with open(self.TOOLS_FILE, "w") as file:
                pass  # Create an empty file

    def load_tools(self):
        if os.path.exists(self.TOOLS_FILE):
            with open(self.TOOLS_FILE, "r") as file:
                for line in file:
                    tool_info = line.strip().split(":")
                    if len(tool_info) == 4:
                        tool_name, launch_command, query, parent_dir = tool_info
                        self.tool_list.addItem(f"{tool_name}: {launch_command} ({query}) in {parent_dir}")
                    else:
                        print(f"Skipping invalid tool info: {line.strip()}")


    def import_tool(self):
        repo_url, ok = QInputDialog.getText(self, "Import Tool", "Enter Git clone URL:")
        if ok:
            tool_name = repo_url.split("/")[-1].replace(".git", "")
            clone_dir = os.path.join(self.imported_dir, repo_url.split("/")[-1].replace(".git", ""))
            if os.path.exists(clone_dir):
                QMessageBox.warning(self, "Error", f"Tool already exists")
                return

            subprocess.run(["git", "clone", repo_url, clone_dir], check=True)
            launch_command = self.command_input.text()
            query = self.query_input.text()
            parent_dir = self.parent_dir_input.text()

            tools_file_dir = os.path.dirname(self.TOOLS_FILE)
            if not os.path.exists(tools_file_dir):
                os.makedirs(tools_file_dir)
            if not os.path.exists(self.TOOLS_FILE):
                open(self.TOOLS_FILE, 'w').close()  # Create an empty file

            self.tool_list.addItem(f"{tool_name}: {launch_command} ({query if query else ''}) in {parent_dir}")
            with open(self.TOOLS_FILE, "a") as file:
                file.write(f"{tool_name}:{launch_command}::{query if query else ''}::{parent_dir}\n")
            QMessageBox.information(self, "Success", f"Tool imported successfully")


    def edit_command(self):
        selected_tool = self.tool_list.currentItem()
        if not selected_tool:
            QMessageBox.warning(self, "No tool selected", "Please select a tool to edit.")
            return

        tool_info = selected_tool.text().split(":")
        if len(tool_info) != 4:
            QMessageBox.warning(self, "Invalid tool info", "The selected tool has invalid information.")
            return

        tool_name, launch_command, query, parent_dir = tool_info

        new_launch_command, ok = QInputDialog.getText(self, "Edit Launch Command", "Enter new launch command:", QLineEdit.Normal, launch_command)
        if ok:
            new_query, ok = QInputDialog.getText(self, "Edit Query", "Enter new query:", QLineEdit.Normal, query)
            if ok:
                new_tool_info = f"{tool_name}:{new_launch_command}:{new_query}:{parent_dir}"
                selected_tool.setText(f"{tool_name}: {new_launch_command} ({new_query}) in {parent_dir}")
                with open(self.TOOLS_FILE, "r") as file:
                    tools = file.readlines()
                with open(self.TOOLS_FILE, "w") as file:
                    for tool in tools:
                        if tool.startswith(tool_name + ":"):
                            file.write(new_tool_info + "\n")
                        else:
                            file.write(tool)



    def delete_tool(self):
        selected_tool = self.tool_list.currentItem()
        if not selected_tool:
            QMessageBox.warning(self, "No tool selected", "Please select a tool to delete.")
            return

        tool_info = selected_tool.text().split(":")
        if len(tool_info) != 4:
            QMessageBox.warning(self, "Invalid tool info", "The selected tool has invalid information.")
            return

        tool_name, launch_command, query, parent_dir = tool_info

        reply = QMessageBox.question(self, "Delete Tool", f"Are you sure you want to delete the tool '{tool_name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            with open(self.TOOLS_FILE, "r") as file:
                tools = file.readlines()
            with open(self.TOOLS_FILE, "w") as file:
                for tool in tools:
                    if not tool.startswith(tool_name + ":"):
                        file.write(tool)
            self.tool_list.takeItem(self.tool_list.row(selected_tool))

            tool_dir = os.path.join(self.imported_dir, tool_name)
            if os.path.exists(tool_dir):
                shutil.rmtree(tool_dir)




    def launch_tool(self):
        selected_tool = self.tool_list.currentItem()
        if not selected_tool:
            QMessageBox.warning(self, "Error", "No tool selected")
            return

        tool_text = selected_tool.text()
        tool_parts = tool_text.split(": ")
        tool_name = tool_parts[0]
        launch_command_parts = tool_parts[1].split(" (")
        launch_command = launch_command_parts[0]
        query_parts = launch_command_parts[1].strip(")").split(" in ")
        query = query_parts[0]
        parent_dir = query_parts[1]

        with open(self.TOOLS_FILE, "r") as file:
            for line in file:
                tool_data = line.strip().split(":")
                if tool_data[0] == tool_name:
                    launch_command = tool_data[1]
                    parent_dir = tool_data[3]
                    break

        script_name = f"{tool_name}.py"
        if query:
            launch_command = f"python3 {script_name} {query}"
        else:
            launch_command = f"python3 {script_name}"
        tool_dir = os.path.join(self.imported_dir, tool_name)
        subprocess.run(launch_command.split(), cwd=tool_dir, check=True)


    def update_imported_tools_list(self):
        # Clear the current list of tools
        self.tool_list.clear()
        # Reload the list of tools from the updated tools file
        self.load_tools()

    def update_tool_command(self, tool_name, new_command):
        tools = []
        with open(self.TOOLS_FILE, "r") as file:
            tools = [line.strip().split("::") for line in file if line.strip()]
        with open(self.TOOLS_FILE, "w") as file:
            for tool in tools:
                if tool[0] == tool_name:
                    file.write(f"{tool_name}::{new_command}\n")
                else:
                    file.write(f"{tool[0]}::{tool[1]}\n")

    def remove_tool_from_file(self, tool_name):
        tools = []
        with open(self.TOOLS_FILE, "r") as file:
            tools = [line.strip().split("::") for line in file if line.strip()]
        with open(self.TOOLS_FILE, "w") as file:
            for tool in tools:
                if tool[0] != tool_name:
                    file.write(f"{tool[0]}::{tool[1]}\n")

    def refresh_tool_list(self):
        self.tool_list.clear()
        self.load_tools()