import sys
import os

# macOS向けの設定をインポート前に行う
os.environ['QT_MAC_WANTS_LAYER'] = '1'
os.environ['QT_QPA_PLATFORM'] = 'cocoa'  # macOS特有の設定

import requests
from bs4 import BeautifulSoup
import re
import csv
import time
import random
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QLineEdit, QFrame, QGroupBox, QSplitter, QMessageBox, QCheckBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QUrl
from PyQt5.QtGui import QFont, QDesktopServices

class ScrapingWorker(QThread):
    progress_updated = pyqtSignal(str, int, int)  # page_number, current, total
    log_updated = pyqtSignal(str)
    finished = pyqtSignal(list)  # 求人リストを渡す
    error_occurred = pyqtSignal(str)

    def __init__(self, url, max_pages=50, remove_duplicates=True):
        super().__init__()
        self.url = url
        self.max_pages = max_pages
        self.stop_requested = False
        self.job_titles = []
        self.remove_duplicates = remove_duplicates
        
        # アクセス制限回避のためのランダム遅延
        self.min_delay = 1.5
        self.max_delay = 3.0
        
        # 一般的なUser-Agentリスト
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]

    def get_random_user_agent(self):
        """ランダムなUser-Agentを返す"""
        return random.choice(self.user_agents)

    def extract_job_titles(self, url, page=1):
        # 最大ページ数を超えたら終了
        if page > self.max_pages or self.stop_requested:
            self.log_updated.emit(f"最大ページ数 ({self.max_pages}) に達したか、停止要求があったため抽出を終了します。")
            return
        
        # ページパラメータを追加
        if page > 1:
            if '?' in url:
                # すでにpage=Nがあれば置き換え、なければ追加
                if 'page=' in url:
                    current_url = re.sub(r'page=\d+', f'page={page}', url)
                else:
                    current_url = f"{url}&page={page}"
            else:
                current_url = f"{url}?page={page}"
        else:
            current_url = url
        
        self.log_updated.emit(f"ページ {page} を処理中... URL: {current_url}")
        self.progress_updated.emit(f"ページ {page}", page, self.max_pages)
        
        # ランダムな遅延を追加してアクセス制限を回避
        delay = random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)
        
        # Send a request to the URL
        headers = {
            'User-Agent': self.get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            'Referer': 'https://job-medley.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        try:
            response = requests.get(current_url, headers=headers)
            
            # Check if the request was successful
            if response.status_code != 200:
                self.log_updated.emit(f"ページの取得に失敗しました: ステータスコード {response.status_code}")
                return
            
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find job titles based on the structure of job-medley.com
            # Look for h3 elements which typically contain job titles
            job_listings = soup.find_all('h3')
            
            # Words that indicate non-job title h3 elements
            ignore_words = ['なるほど', '会員登録', '正社員', 'パート', 'バイト', 'スカウト', '希望', '会員限定']
            
            # 現在のページのタイトル数
            page_titles_count = 0
            
            for listing in job_listings:
                if self.stop_requested:
                    self.log_updated.emit("停止要求があったため処理を中断します。")
                    return
                
                # Clean up the text (remove extra whitespace and newlines)
                title = listing.text.strip()
                
                # Check if this is a real job title or navigation element
                should_ignore = False
                for word in ignore_words:
                    if word in title:
                        should_ignore = True
                        break
                
                if title and not should_ignore:
                    self.job_titles.append({'page': page, 'title': title})
                    page_titles_count += 1
            
            self.log_updated.emit(f"  {page_titles_count} 件の求人を見つけました")
            
            # 次のページへのリンクを複数の方法で探す
            next_page = None
            
            # 方法1: ページネーションリンクを探す
            pagination_links = soup.select('div.pagination a, ul.pagination a, nav.pagination a')
            for link in pagination_links:
                link_text = link.text.strip()
                href = link.get('href', '')
                # 「次へ」「次のページ」などのテキストを持つリンクを探す
                if '次' in link_text or ('page=' in href and f'page={page+1}' in href):
                    next_page = link
                    self.log_updated.emit(f"  次のページへのリンクを見つけました: {link.get('href')}")
                    break
            
            # 方法2: ページ番号のリンクから次のページを探す
            if not next_page:
                page_num_links = soup.select('a[href*="page="]')
                for link in page_num_links:
                    page_num_match = re.search(r'page=(\d+)', link.get('href', ''))
                    if page_num_match:
                        found_page = int(page_num_match.group(1))
                        if found_page == page + 1:
                            next_page = link
                            self.log_updated.emit(f"  次のページ({found_page})へのリンクを見つけました: {link.get('href')}")
                            break
            
            # 次のページが存在し、現在のページで求人が見つかった場合は続行
            if next_page and page_titles_count > 0 and not self.stop_requested:
                self.extract_job_titles(url, page + 1)
            elif page_titles_count > 0 and not self.stop_requested:
                # 次のページへのリンクがないが、このページに求人がある場合は
                # 単純にページ番号を進めてみる
                self.log_updated.emit("  明示的な次ページリンクが見つかりませんでしたが、次のページを試みます")
                self.extract_job_titles(url, page + 1)
                
        except Exception as e:
            self.log_updated.emit(f"エラーが発生しました: {str(e)}")
            self.error_occurred.emit(f"エラーが発生しました: {str(e)}")

    def remove_duplicate_titles(self, job_titles):
        """タイトルが重複している求人を削除し、ユニークなリストを返す"""
        self.log_updated.emit("重複する求人タイトルを削除しています...")
        
        unique_titles = []
        seen_titles = set()
        
        for job in job_titles:
            title = job['title']
            if title not in seen_titles:
                seen_titles.add(title)
                unique_titles.append(job)
                
        removed_count = len(job_titles) - len(unique_titles)
        self.log_updated.emit(f"重複する {removed_count} 件の求人タイトルを削除しました。")
        
        return unique_titles

    def run(self):
        try:
            self.log_updated.emit("求人サイトから職場名を抽出を開始します...")
            self.job_titles = []
            self.extract_job_titles(self.url)
            
            if self.job_titles:
                # 重複を削除する場合
                if self.remove_duplicates:
                    original_count = len(self.job_titles)
                    self.job_titles = self.remove_duplicate_titles(self.job_titles)
                    self.log_updated.emit(f"元の求人数: {original_count}件、ユニークな求人数: {len(self.job_titles)}件")
                
                # ページごとの統計を計算
                page_counts = {}
                for title in self.job_titles:
                    page = title['page']
                    if page not in page_counts:
                        page_counts[page] = 0
                    page_counts[page] += 1
                
                self.log_updated.emit(f"\n合計 {len(self.job_titles)} 件の求人が見つかりました。")
                
                self.log_updated.emit("\nページごとの求人数:")
                for page, count in sorted(page_counts.items()):
                    self.log_updated.emit(f"  ページ {page}: {count} 件")
                
                # 結果を返す
                self.finished.emit(self.job_titles)
            else:
                self.log_updated.emit("求人情報が見つかりませんでした。")
                self.finished.emit([])
                
        except Exception as e:
            self.log_updated.emit(f"処理中にエラーが発生しました: {str(e)}")
            self.error_occurred.emit(f"処理中にエラーが発生しました: {str(e)}")
            self.finished.emit([])
            
    def stop(self):
        self.stop_requested = True
        self.log_updated.emit("停止要求を受け付けました。処理を停止します...")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scraping_worker = None
        self.job_titles = []
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Job Medley スクレイピングツール")
        self.setGeometry(100, 100, 900, 700)
        
        # メインウィジェットとレイアウトの設定
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # URL入力エリア
        url_group = QGroupBox("URLを入力")
        url_layout = QHBoxLayout()
        
        # デフォルトURL
        default_url = "https://job-medley.com/ans/search/?job_category_code=ans&prefecture_id=13&city_id%5B%5D=13101&city_id%5B%5D=13102&city_id%5B%5D=13103&city_id%5B%5D=13104&city_id%5B%5D=13105&city_id%5B%5D=13106&city_id%5B%5D=13107&city_id%5B%5D=13108&city_id%5B%5D=13109&city_id%5B%5D=13110&city_id%5B%5D=13111&city_id%5B%5D=13112&city_id%5B%5D=13113&city_id%5B%5D=13114&city_id%5B%5D=13115&city_id%5B%5D=13116&city_id%5B%5D=13117&city_id%5B%5D=13118&city_id%5B%5D=13119&city_id%5B%5D=13120&city_id%5B%5D=13121&city_id%5B%5D=13122&city_id%5B%5D=13123&designated_city_id=4&hw=1"
        self.url_edit = QLineEdit(default_url)
        url_layout.addWidget(self.url_edit)
        url_group.setLayout(url_layout)
        main_layout.addWidget(url_group)
        
        # 設定エリア
        settings_group = QGroupBox("設定")
        settings_layout = QHBoxLayout()
        
        settings_layout.addWidget(QLabel("最大ページ数:"))
        self.max_pages_edit = QLineEdit("50")
        self.max_pages_edit.setFixedWidth(50)
        settings_layout.addWidget(self.max_pages_edit)
        
        settings_layout.addSpacing(20)
        
        # 重複削除オプション
        self.remove_duplicates_checkbox = QCheckBox("重複する求人タイトルを削除")
        self.remove_duplicates_checkbox.setChecked(True)
        settings_layout.addWidget(self.remove_duplicates_checkbox)
        
        settings_layout.addStretch(1)
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("スクレイピング開始")
        self.start_button.clicked.connect(self.start_scraping)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_scraping)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        self.save_button = QPushButton("CSVに保存")
        self.save_button.clicked.connect(self.save_to_csv)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)
        
        button_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        
        # 進捗表示エリア
        progress_group = QGroupBox("進捗状況")
        progress_layout = QVBoxLayout()
        
        self.progress_label = QLabel("待機中...")
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)
        
        # ログ表示エリア
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        font = QFont("Monospace", 10)
        self.log_text.setFont(font)
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, 1)
        
        # 初期ログメッセージ
        self.log("アプリケーションが起動しました。URLを確認して「スクレイピング開始」ボタンをクリックしてください。")
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 自動スクロール
        self.log_text.ensureCursorVisible()
    
    def update_progress(self, label_text, current, total):
        self.progress_label.setText(f"{label_text} - {current}/{total}")
        self.progress_bar.setValue(int(current / total * 100))
    
    def start_scraping(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "エラー", "URLを入力してください。")
            return
        
        try:
            max_pages = int(self.max_pages_edit.text())
            if max_pages <= 0:
                raise ValueError("最大ページ数は1以上の整数を指定してください。")
        except ValueError as e:
            QMessageBox.warning(self, "エラー", f"最大ページ数の指定が不正です: {str(e)}")
            return
        
        # UIの更新
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.save_button.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # 重複削除オプションの取得
        remove_duplicates = self.remove_duplicates_checkbox.isChecked()
        
        # ワーカーの設定と開始
        self.scraping_worker = ScrapingWorker(url, max_pages, remove_duplicates)
        self.scraping_worker.log_updated.connect(self.log)
        self.scraping_worker.progress_updated.connect(self.update_progress)
        self.scraping_worker.finished.connect(self.scraping_finished)
        self.scraping_worker.error_occurred.connect(self.handle_error)
        self.scraping_worker.start()
    
    def stop_scraping(self):
        if self.scraping_worker and self.scraping_worker.isRunning():
            self.scraping_worker.stop()
            self.log("停止を要求しました。処理が完了するまでお待ちください...")
            self.stop_button.setEnabled(False)
    
    def scraping_finished(self, job_titles):
        self.job_titles = job_titles
        self.log("処理が完了しました。")
        
        # UIの更新
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.save_button.setEnabled(len(job_titles) > 0)
        
        if job_titles:
            # 完了ポップアップを表示
            QMessageBox.information(self, "完了", "スクレイピングが完了しました！")
        else:
            self.log("求人情報が見つかりませんでした。")
            QMessageBox.warning(self, "完了", "求人情報が見つかりませんでした。")
    
    def handle_error(self, error_message):
        self.log(f"エラー: {error_message}")
        QMessageBox.warning(self, "エラー", error_message)
        
        # UIの更新
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def save_to_csv(self):
        if not self.job_titles:
            QMessageBox.information(self, "情報", "保存するデータがありません。")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSVファイルを保存", "", "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['page', 'title']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for title in self.job_titles:
                        writer.writerow(title)
                
                self.log(f"結果を {file_path} に保存しました。")
                QMessageBox.information(self, "成功", f"{len(self.job_titles)}件の求人情報を保存しました。")
            except Exception as e:
                error_message = f"CSVファイルの保存中にエラーが発生しました: {str(e)}"
                self.log(error_message)
                QMessageBox.warning(self, "エラー", error_message)

    def closeEvent(self, event):
        # アプリケーション終了時にスレッドを停止
        if self.scraping_worker and self.scraping_worker.isRunning():
            reply = QMessageBox.question(
                self, '確認', 
                "スクレイピングが実行中です。終了しますか？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.scraping_worker.stop()
                self.scraping_worker.wait()  # スレッド終了を待機
            else:
                event.ignore()
                return
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main() 