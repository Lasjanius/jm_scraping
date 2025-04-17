import requests
from bs4 import BeautifulSoup
import re
import csv
import time
import random
import os

def extract_job_titles(url, page=1, all_titles=None, max_pages=50):
    if all_titles is None:
        all_titles = []
    
    # 最大ページ数を超えたら終了
    if page > max_pages:
        print(f"最大ページ数 ({max_pages}) に達しました。抽出を終了します。")
        return all_titles
    
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
    
    print(f"ページ {page} を処理中... URL: {current_url}")
    
    # ランダムな遅延を追加してアクセス制限を回避
    delay = random.uniform(1.5, 3.0)
    time.sleep(delay)
    
    # Send a request to the URL
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
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
            print(f"ページの取得に失敗しました: ステータスコード {response.status_code}")
            return all_titles
        
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
            # Clean up the text (remove extra whitespace and newlines)
            title = listing.text.strip()
            
            # Check if this is a real job title or navigation element
            should_ignore = False
            for word in ignore_words:
                if word in title:
                    should_ignore = True
                    break
            
            if title and not should_ignore:
                all_titles.append({'page': page, 'title': title})
                page_titles_count += 1
        
        print(f"  {page_titles_count} 件の求人を見つけました")
        
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
                print(f"  次のページへのリンクを見つけました: {link.get('href')}")
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
                        print(f"  次のページ({found_page})へのリンクを見つけました: {link.get('href')}")
                        break
        
        # 次のページが存在し、現在のページで求人が見つかった場合は続行
        if next_page and page_titles_count > 0:
            return extract_job_titles(url, page + 1, all_titles, max_pages)
        elif page_titles_count > 0:
            # 次のページへのリンクがないが、このページに求人がある場合は
            # 単純にページ番号を進めてみる
            print("  明示的な次ページリンクが見つかりませんでしたが、次のページを試みます")
            return extract_job_titles(url, page + 1, all_titles, max_pages)
        else:
            print("最後のページに到達したか、次のページで求人が見つかりませんでした。抽出を終了します。")
            return all_titles
            
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return all_titles

def save_to_csv(job_titles, filename="job_medley_results.csv"):
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['page', 'title']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for title in job_titles:
                writer.writerow(title)
        
        print(f"結果を {filename} に保存しました。")
        return True
    except Exception as e:
        print(f"CSVファイルの保存中にエラーが発生しました: {str(e)}")
        return False

def main(test_mode=True):
    # URL from the provided example
    url = "https://job-medley.com/ans/search/?job_category_code=ans&prefecture_id=13&city_id%5B%5D=13101&city_id%5B%5D=13102&city_id%5B%5D=13103&city_id%5B%5D=13104&city_id%5B%5D=13105&city_id%5B%5D=13106&city_id%5B%5D=13107&city_id%5B%5D=13108&city_id%5B%5D=13109&city_id%5B%5D=13110&city_id%5B%5D=13111&city_id%5B%5D=13112&city_id%5B%5D=13113&city_id%5B%5D=13114&city_id%5B%5D=13115&city_id%5B%5D=13116&city_id%5B%5D=13117&city_id%5B%5D=13118&city_id%5B%5D=13119&city_id%5B%5D=13120&city_id%5B%5D=13121&city_id%5B%5D=13122&city_id%5B%5D=13123&designated_city_id=4&hw=1"
    
    if test_mode:
        print("テストモードで実行中...")
        # テストモードでは3ページまで処理
        max_pages = 3
        filename = "test_job_medley_results.csv"
    else:
        print("本番モードで実行中...")
        max_pages = 50  # 最大ページ数を設定
        filename = "job_medley_results.csv"
    
    print("求人サイトから職場名を抽出しています...")
    job_titles = extract_job_titles(url, max_pages=max_pages)
    
    if job_titles:
        print(f"\n合計 {len(job_titles)} 件の求人が見つかりました。")
        
        # ページごとの統計を表示
        page_counts = {}
        for title in job_titles:
            page = title['page']
            if page not in page_counts:
                page_counts[page] = 0
            page_counts[page] += 1
        
        print("\nページごとの求人数:")
        for page, count in sorted(page_counts.items()):
            print(f"  ページ {page}: {count} 件")
        
        # CSVに保存
        save_success = save_to_csv(job_titles, filename)
        
        if save_success and test_mode:
            print("テストが成功しました。本番モードで実行します...")
            main(test_mode=False)
    else:
        print("求人情報が見つかりませんでした。")

# テストモードで実行
if __name__ == "__main__":
    main(test_mode=True)
