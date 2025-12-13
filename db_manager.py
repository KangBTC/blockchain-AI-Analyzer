import sqlite3
import json
import os

# ========== 数据库文件路径配置 ==========
# 定义数据库目录和文件路径
DB_DIR_ADDRESS = 'data/sql/address'           # 交易数据库目录
DB_DIR_LABELS = 'data/sql/address_labels'     # 地址标签数据库目录
DB_DIR_CHAT = 'data/sql/chat'                 # 聊天记录数据库目录（每个地址一个数据库文件）
DB_PATH_TRANSACTIONS = os.path.join(DB_DIR_ADDRESS, 'transactions.db')  # 交易数据库文件路径
DB_PATH_LABELS = os.path.join(DB_DIR_LABELS, 'labels.db')               # 地址标签数据库文件路径

def setup_databases():
    """
    准备好数据库，如果还没有就创建
    """
    # ========== 创建数据库目录 ==========
    os.makedirs(DB_DIR_ADDRESS, exist_ok=True)
    os.makedirs(DB_DIR_LABELS, exist_ok=True)
    os.makedirs(DB_DIR_CHAT, exist_ok=True)  # 创建聊天记录目录

    # ========== 创建交易数据库和表 ==========
    with sqlite3.connect(DB_PATH_TRANSACTIONS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            txHash TEXT PRIMARY KEY,              -- 交易哈希（主键）
            chainIndex TEXT NOT NULL,             -- 链ID
            queriedAddress TEXT NOT NULL,         -- 查询的地址
            transactionDetailJson TEXT NOT NULL   -- 交易详情（JSON字符串）
        )
        """)
        # ========== 检查并添加 ai_analysis 列 ==========
        cursor.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'ai_analysis' not in columns:
            cursor.execute("ALTER TABLE transactions ADD COLUMN ai_analysis TEXT")
        conn.commit()

    # ========== 创建地址标签数据库和表 ==========
    with sqlite3.connect(DB_PATH_LABELS) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            address TEXT PRIMARY KEY,    -- 地址（主键，小写）
            labelJson TEXT NOT NULL      -- 标签信息（JSON字符串）
        )
        """)
        conn.commit()

# ========== 交易数据库操作 ==========

def add_transaction_detail(txHash: str, chainIndex: str, queriedAddress: str, detail_data: dict):
    with sqlite3.connect(DB_PATH_TRANSACTIONS) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO transactions (txHash, chainIndex, queriedAddress, transactionDetailJson) VALUES (?, ?, ?, ?)",
            (txHash, chainIndex, queriedAddress, json.dumps(detail_data))
        )
        conn.commit()

def get_transaction_details_by_hashes(txHashes: list[str]) -> dict[str, dict]:
    if not txHashes:
        return {}
    
    with sqlite3.connect(DB_PATH_TRANSACTIONS) as conn:
        cursor = conn.cursor()
        query = f"SELECT txHash, transactionDetailJson, ai_analysis FROM transactions WHERE txHash IN ({','.join(['?']*len(txHashes))})"
        cursor.execute(query, txHashes)
        
        results = {}
        for row in cursor.fetchall():
            txHash, detail_json, ai_analysis = row
            results[txHash] = {
                "detail": json.loads(detail_json),
                "analysis": ai_analysis
            }
        return results

def update_ai_analysis(txHash: str, analysis: str):
    with sqlite3.connect(DB_PATH_TRANSACTIONS) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE transactions SET ai_analysis = ? WHERE txHash = ?",
            (analysis, txHash)
        )
        conn.commit()

# ========== 地址标签数据库操作 ==========

def add_labels(label_data: dict[str, dict]):
    if not label_data:
        return
    to_insert = [(address.lower(), json.dumps(data)) for address, data in label_data.items()]
    
    with sqlite3.connect(DB_PATH_LABELS) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT OR REPLACE INTO labels (address, labelJson) VALUES (?, ?)",
            to_insert
        )
        conn.commit()

def get_labels_by_addresses(addresses: list[str]) -> dict[str, dict]:
    if not addresses:
        return {}
    addresses_lower = [addr.lower() for addr in addresses]
    
    with sqlite3.connect(DB_PATH_LABELS) as conn:
        cursor = conn.cursor()
        query = f"SELECT address, labelJson FROM labels WHERE address IN ({','.join(['?']*len(addresses_lower))})"
        cursor.execute(query, addresses_lower)
        
        results = {}
        for row in cursor.fetchall():
            address, label_json = row
            results[address] = json.loads(label_json)
        return results

# ========== 聊天记录数据库操作 ==========

def get_chat_db_path(address: str) -> str:
    return os.path.join(DB_DIR_CHAT, f"{address}.db")

def setup_chat_database(address: str):
    db_path = get_chat_db_path(address)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS context (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """)
        conn.commit()

def reset_chat_history(address: str):
    """
    清空某个地址的聊天记录（保留context，只清空对话历史）
    用于重新开始分析时，避免旧的对话混入
    """
    db_path = get_chat_db_path(address)
    if os.path.exists(db_path):
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history") # 清空历史表
            conn.commit()

def save_chat_context(address: str, report: str, analyses_summary: str):
    db_path = get_chat_db_path(address)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO context (key, value) VALUES ('report', ?)", (report,))
        cursor.execute("INSERT OR REPLACE INTO context (key, value) VALUES ('analyses_summary', ?)", (analyses_summary,))
        conn.commit()

def save_chat_message(address: str, role: str, content: str):
    db_path = get_chat_db_path(address)
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO history (role, content) VALUES (?, ?)", (role, content))
            conn.commit()
    except Exception as e:
        print(f"保存聊天记录时出错: {e}")

def load_chat_session(address: str) -> tuple[str, str, list]:
    db_path = get_chat_db_path(address)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM context WHERE key = 'report'")
        row = cursor.fetchone()
        report = row[0] if row else ""
        
        cursor.execute("SELECT value FROM context WHERE key = 'analyses_summary'")
        row = cursor.fetchone()
        analyses_summary = row[0] if row else ""
        
        cursor.execute("SELECT role, content FROM history ORDER BY id ASC")
        history = [{"role": role, "content": content} for role, content in cursor.fetchall()]
        return report, analyses_summary, history

def list_available_chats() -> list[str]:
    if not os.path.exists(DB_DIR_CHAT):
        return []
    files = [f for f in os.listdir(DB_DIR_CHAT) if f.endswith('.db')]
    addresses = [os.path.splitext(f)[0] for f in files]
    return addresses
