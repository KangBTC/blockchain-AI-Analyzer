import json
import os
import streamlit as st
from supabase import create_client, Client

# ========== 数据库连接管理 ==========

# 全局客户端实例
_supabase_client = None

def get_supabase() -> Client:
    """
    获取 Supabase 客户端实例（单例模式）
    优先从 Streamlit Secrets 读取配置
    """
    global _supabase_client
    if _supabase_client:
        return _supabase_client
    
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        # 如果在本地运行且没有配置 secrets，尝试读取环境变量或报错
        # 为了简化，这里直接报错提示
        raise ValueError("❌ 未找到 Supabase 配置！请在 .streamlit/secrets.toml 中配置 SUPABASE_URL 和 SUPABASE_KEY。")

def setup_databases():
    """
    Supabase 模式下，不需要本地建表（表已经在 Supabase 网页端建好了）。
    这里只做简单的连接测试。
    """
    try:
        client = get_supabase()
        # 简单测试一下连接
        client.table("transactions").select("count", count="exact").limit(0).execute()
        # print("✅ Supabase 连接成功")
    except Exception as e:
        st.error(f"⚠️ 数据库连接失败: {str(e)}")

# ========== 交易数据库操作 ==========

def add_transaction_detail(txHash: str, chainIndex: str, queriedAddress: str, detail_data: dict):
    """保存交易详情"""
    try:
        client = get_supabase()
        data = {
            "tx_hash": txHash,
            "chain_index": chainIndex,
            "queried_address": queriedAddress,
            "transaction_detail_json": detail_data
        }
        # upsert=True 表示如果主键存在则更新
        client.table("transactions").upsert(data).execute()
    except Exception as e:
        print(f"Error saving transaction: {e}")

def get_transaction_details_by_hashes(txHashes: list[str]) -> dict[str, dict]:
    """批量获取交易详情"""
    if not txHashes:
        return {}
    
    try:
        client = get_supabase()
        # 使用 in_ 过滤器批量查询
        response = client.table("transactions").select("tx_hash, transaction_detail_json, ai_analysis").in_("tx_hash", txHashes).execute()
        
        results = {}
        for item in response.data:
            results[item['tx_hash']] = {
                "detail": item['transaction_detail_json'], # Supabase 会自动解析 JSONB
                "analysis": item.get('ai_analysis')
            }
        return results
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        return {}

def update_ai_analysis(txHash: str, analysis: str):
    """更新 AI 分析结果"""
    try:
        client = get_supabase()
        client.table("transactions").update({"ai_analysis": analysis}).eq("tx_hash", txHash).execute()
    except Exception as e:
        print(f"Error updating analysis: {e}")

# ========== 地址标签数据库操作 ==========

def add_labels(label_data: dict[str, dict]):
    """批量保存地址标签"""
    if not label_data:
        return
        
    try:
        client = get_supabase()
        to_insert = [
            {"address": address.lower(), "label_json": data}
            for address, data in label_data.items()
        ]
        client.table("labels").upsert(to_insert).execute()
    except Exception as e:
        print(f"Error saving labels: {e}")

def get_labels_by_addresses(addresses: list[str]) -> dict[str, dict]:
    """批量获取地址标签"""
    if not addresses:
        return {}
    
    try:
        client = get_supabase()
        addresses_lower = [addr.lower() for addr in addresses]
        response = client.table("labels").select("address, label_json").in_("address", addresses_lower).execute()
        
        results = {}
        for item in response.data:
            results[item['address']] = item['label_json']
        return results
    except Exception as e:
        print(f"Error fetching labels: {e}")
        return {}

# ========== 聊天记录数据库操作 ==========

def reset_chat_history(address: str):
    """清空某个地址的聊天记录"""
    try:
        client = get_supabase()
        # 删除 chat_history 表中该地址的所有记录
        client.table("chat_history").delete().eq("address", address).execute()
    except Exception as e:
        print(f"Error resetting chat history: {e}")

def save_chat_context(address: str, report: str, analyses_summary: str):
    """保存聊天上下文（报告和摘要）"""
    try:
        client = get_supabase()
        data = {
            "address": address,
            "report": report,
            "analyses_summary": analyses_summary,
            "updated_at": "now()"
        }
        client.table("chat_context").upsert(data).execute()
    except Exception as e:
        print(f"Error saving context: {e}")

def save_chat_message(address: str, role: str, content: str):
    """保存一条聊天记录"""
    try:
        client = get_supabase()
        data = {
            "address": address,
            "role": role,
            "content": content
        }
        client.table("chat_history").insert(data).execute()
    except Exception as e:
        print(f"Error saving message: {e}")

def load_chat_session(address: str) -> tuple[str, str, list]:
    """加载完整的会话数据"""
    try:
        client = get_supabase()
        
        # 1. 获取上下文 (Context)
        ctx_resp = client.table("chat_context").select("report, analyses_summary").eq("address", address).execute()
        
        report = ""
        analyses_summary = ""
        if ctx_resp.data:
            report = ctx_resp.data[0].get("report", "")
            analyses_summary = ctx_resp.data[0].get("analyses_summary", "")
            
        # 2. 获取历史消息 (History) - 按 ID 升序
        hist_resp = client.table("chat_history").select("role, content").eq("address", address).order("id").execute()
        
        history = hist_resp.data if hist_resp.data else []
        
        return report, analyses_summary, history
    except Exception as e:
        st.error(f"加载历史记录失败: {e}")
        return "", "", []

def list_available_chats() -> list[str]:
    """列出所有已分析的地址"""
    try:
        client = get_supabase()
        # 查询 chat_context 表中的所有地址
        response = client.table("chat_context").select("address").order("updated_at", desc=True).execute()
        
        return [item['address'] for item in response.data]
    except Exception as e:
        # 首次运行时可能表为空，不报错
        return []
