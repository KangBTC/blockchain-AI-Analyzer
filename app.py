import streamlit as st
import pandas as pd
import json
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入现有后端模块
import okx_api_client
import ai_client
import arkham_client
import ai_conclusion
from okx_api_client import get_transactions_by_address, get_transaction_detail_by_hash
from data_processor import extract_tx_info_from_summary, process_and_clean_details
from ai_client import analyze_transaction
from arkham_client import get_arkham_intelligence
from ai_conclusion import generate_conclusion, chat_with_report
from db_manager import (
    get_transaction_details_by_hashes, add_transaction_detail, 
    get_labels_by_addresses, add_labels, update_ai_analysis,
    setup_databases, list_available_chats, load_chat_session,
    reset_chat_history, save_chat_context
)

# ========== 页面配置 ==========
st.set_page_config(
    page_title="AI 链上侦探",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== 全局常量：链配置 ==========
CHAIN_MAP = {
    # EVM 链
    "1": "Ethereum Mainnet (ETH)",
    "56": "BNB Smart Chain (BSC)",
    "137": "Polygon Mainnet",
    "42161": "Arbitrum One",
    "10": "OP Mainnet",
    "8453": "Base",
    "59144": "Linea",
    "324": "zkSync Era",
    "43114": "Avalanche C-Chain",
    "196": "X layer",
    "1101": "Polygon zkEVM",
    "146": "Sonic",
    "130": "Uni Chain",
    "250": "Fantom Opera",
    "5000": "Mantle",
    "1030": "Conflux eSpace",
    "1088": "Metis Andromeda",
    "4200": "Merlin Chain",
    "81457": "Blast",
    "169": "Manta Pacific",
    "534352": "Scroll",
    "25": "Cronos Mainnet",
    "7000": "ZetaChain",
    "9745": "Plasma",
    "143": "Monad",
    # 非 EVM 链
    "195": "Tron",
    "501": "Solana",
    "784": "SUI",
    "607": "Ton"
}

SORTED_CHAIN_IDS = ["1", "56", "137", "42161", "10", "195", "501"] + sorted(
    [k for k in CHAIN_MAP.keys() if k not in ["1", "56", "137", "42161", "10", "195", "501"]],
    key=lambda x: CHAIN_MAP[x]
)

# ========== CSS 美化 ==========
st.markdown("""
<style>
    .report-text {
        font-family: 'Helvetica Neue', sans-serif;
        line-height: 1.6;
        color: #e0e0e0;
    }
    .stButton>button {
        width: 100%;
        border-radius: 20px;
        background-color: #FF4B4B;
        color: white;
    }
    .highlight-box {
        padding: 20px;
        background-color: #262730;
        border-radius: 10px;
        border-left: 5px solid #FF4B4B;
        margin-bottom: 20px;
    }
    .stChatInput {
        padding-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ========== 配置验证 ==========
# 所有 API Key 现在都从 .streamlit/secrets.toml 读取
# 各模块会自动从 st.secrets 读取配置，这里只做简单的验证提示
try:
    required_keys = ["OPENROUTER_API_KEY", "OKX_API_KEY", "OKX_SECRET_KEY", "OKX_PASSPHRASE", "APIFY_API_TOKEN"]
    missing_keys = [key for key in required_keys if key not in st.secrets]
    if missing_keys:
        st.warning(f"⚠️ 缺少必要的配置项: {', '.join(missing_keys)}。请检查 .streamlit/secrets.toml 文件。")
except FileNotFoundError:
    st.error("❌ 未找到配置文件！请创建 .streamlit/secrets.toml 并填入 API Key。")

# ========== Session State 初始化 ==========
if "messages" not in st.session_state:
    st.session_state.messages = []
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "report_content" not in st.session_state:
    st.session_state.report_content = ""
if "analyses_summary" not in st.session_state:
    st.session_state.analyses_summary = ""
if "processed_txs" not in st.session_state:
    st.session_state.processed_txs = []
if "current_address" not in st.session_state:
    st.session_state.current_address = ""

# 初始化数据库（确保目录存在）
setup_databases()

# ========== 侧边栏 ==========
with st.sidebar:
    st.title("🕵️‍♂️ 配置中心")
    
    # --- 历史记录功能 ---
    st.markdown("### 📂 历史档案")
    available_chats = list_available_chats()
    
    # 增加一个 "请选择" 的默认选项
    history_options = ["请选择..."] + available_chats
    
    selected_history = st.selectbox(
        "恢复之前的调查",
        options=history_options,
        index=0,
        help="选择一个地址以恢复之前的分析报告和对话记录"
    )
    
    # 如果用户选择了某个历史记录，且跟当前显示的不仅仅是同一个
    if selected_history != "请选择..." and selected_history != st.session_state.current_address:
        if st.button("📥 加载档案"):
            try:
                with st.spinner(f"正在读取 {selected_history} 的档案..."):
                    report, analyses_summary, history = load_chat_session(selected_history)
                    
                    # 恢复状态
                    st.session_state.report_content = report
                    st.session_state.analyses_summary = analyses_summary
                    st.session_state.current_address = selected_history
                    st.session_state.analysis_done = True
                    st.session_state.processed_txs = [] # 历史记录暂不恢复原始交易详情
                    
                    # 恢复对话历史
                    restored_msgs = []
                    for msg in history:
                        role = "assistant" if msg['role'] == "assistant" else "user"
                        restored_msgs.append({"role": role, "content": msg['content']})
                    
                    st.session_state.messages = restored_msgs
                    
                    # 如果没有历史消息，添加默认欢迎语
                    if not st.session_state.messages:
                         st.session_state.messages = [{"role": "assistant", "content": "历史档案加载完毕。您可以继续对该地址进行提问。"}]
                    
                    st.success("档案加载成功！")
                    time.sleep(0.5)
                    st.rerun()
            except Exception as e:
                st.error(f"加载失败: {str(e)}")

    st.markdown("---")
    
    # --- 新分析配置 ---
    st.markdown("### 🎯 新任务设置")
    
    target_chain = st.selectbox(
        "选择区块链",
        options=SORTED_CHAIN_IDS,
        format_func=lambda x: CHAIN_MAP.get(x, f"Unknown ({x})")
    )
    
    tx_limit = st.slider("分析交易数量", min_value=5, max_value=50, value=10, step=5)
    
    st.markdown("---")
    if st.button("🗑️ 清空当前会话"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ========== 主界面 ==========
st.title("AI 链上行为分析器")

# 地址输入区
if not st.session_state.analysis_done:
    st.markdown("输入任何钱包地址，AI 将为您生成深度行为画像、资金流向分析以及风险评估。")
    col1, col2 = st.columns([3, 1])
    with col1:
        target_address = st.text_input("钱包地址", placeholder="例如: 0x1234...", key="addr_input")
    with col2:
        st.write("") 
        st.write("")
        start_btn = st.button("🚀 开始侦查")
else:
    st.caption(f"当前调查目标: `{st.session_state.current_address}`")
    if st.button("🔍 调查新地址"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    start_btn = False

# ========== 核心分析逻辑 ==========
if start_btn and target_address:
    if len(target_address) < 10:
        st.error("请输入有效的钱包地址！")
    else:
        status_container = st.container()
        progress_bar = st.progress(0)
        
        with status_container:
            st.info(f"正在启动分析引擎... 目标: {target_address} ({CHAIN_MAP.get(target_chain)})")
            
            try:
                # 关键修复：如果是新分析，先清空该地址的旧聊天记录
                # 避免新报告生成后，下面还挂着驴唇不对马嘴的旧对话
                reset_chat_history(target_address)
                
                # --- 步骤 1: 获取交易摘要 ---
                progress_bar.progress(10, text="📡 正在扫描链上数据 (OKX API)...")
                raw_summary = get_transactions_by_address(target_address, target_chain, tx_limit)
                
                if not raw_summary:
                    st.error("未找到该地址的交易记录。请确认地址和链选择正确。")
                    st.stop()
                    
                tx_info_list = extract_tx_info_from_summary(raw_summary)
                
                # 去重
                unique_tx_hashes = set()
                unique_tx_info = []
                for tx in tx_info_list:
                    if tx['txHash'] not in unique_tx_hashes:
                        unique_tx_hashes.add(tx['txHash'])
                        unique_tx_info.append(tx)
                
                st.write(f"✅ 发现 {len(unique_tx_info)} 条最近交易")
                
                # --- 步骤 2: 缓存检查与详情获取 ---
                progress_bar.progress(30, text="🔍 正在获取交易深度详情...")
                
                hashes_to_check = [tx['txHash'] for tx in unique_tx_info]
                cached_data = get_transaction_details_by_hashes(hashes_to_check)
                
                all_details_raw = [item['detail'] for item in cached_data.values()]
                to_fetch = [tx for tx in unique_tx_info if tx['txHash'] not in cached_data]
                
                if to_fetch:
                    fetch_ph = st.empty()
                    for i, tx in enumerate(to_fetch):
                        fetch_ph.write(f"正在下载交易详情 ({i+1}/{len(to_fetch)}): {tx['txHash'][:10]}...")
                        try:
                            detail = get_transaction_detail_by_hash(tx['chainIndex'], tx['txHash'])
                            if detail:
                                all_details_raw.extend(detail)
                                for d in detail:
                                    add_transaction_detail(d['txhash'], d['chainIndex'], target_address, d)
                        except Exception as e:
                            st.warning(f"获取交易 {tx['txHash']} 失败: {e}")
                        time.sleep(1.1)  # 与 core_logic.py 保持一致，避免API限流
                    fetch_ph.empty()
                
                # --- 步骤 3: 数据清洗与标签获取 ---
                progress_bar.progress(50, text="🏷️ 正在识别地址身份 (Arkham Intelligence)...")
                processed_data = process_and_clean_details(all_details_raw, target_address)
                # 将处理后的数据转换为字典，以交易哈希为键，方便后续查找
                processed_data_map = {tx['txhash']: tx for tx in processed_data}
                
                # 辅助函数：从字段中提取地址
                # 因为地址可能以字符串或字典形式存储，需要统一处理
                def get_address_from_field(field_value):
                    """从字段值中提取地址，支持字符串和字典两种格式"""
                    if isinstance(field_value, dict):
                        return field_value.get('address')
                    elif isinstance(field_value, str):
                        return field_value
                    return None
                
                # 收集地址（包括主交易、内部交易、代币转账中的所有地址）
                all_addrs = set()
                for tx in processed_data:
                    # 主交易的 from/to
                    all_addrs.add(tx['from']['address'])
                    all_addrs.add(tx['to']['address'])
                    # 内部交易中的地址
                    for itx in tx.get('internalTransactions', []):
                        all_addrs.add(get_address_from_field(itx.get('from')))
                        all_addrs.add(get_address_from_field(itx.get('to')))
                    # 代币转账中的地址
                    for ttx in tx.get('tokenTransfers', []):
                        all_addrs.add(get_address_from_field(ttx.get('from')))
                        all_addrs.add(get_address_from_field(ttx.get('to')))
                # 移除空值
                all_addrs.discard(None)
                all_addrs.discard("")
                
                # 获取标签
                cached_labels = get_labels_by_addresses(list(all_addrs))
                new_addrs = [a for a in list(all_addrs) if a.lower() not in cached_labels]
                
                arkham_data = cached_labels
                if new_addrs:
                    st.write(f"正在为 {len(new_addrs)} 个新地址获取身份标签...")
                    new_labels = get_arkham_intelligence(new_addrs)
                    if new_labels:
                        add_labels(new_labels)
                        arkham_data.update({k.lower(): v for k, v in new_labels.items()})
                
                # 注入标签（主交易 + 内部交易 + 代币转账）
                def enrich_address_field(target_dict, address_key):
                    """
                    为地址字段添加标签信息
                    
                    参数:
                        target_dict: 包含地址字段的字典（例如：tx, itx, ttx）
                        address_key: 地址字段的键名（'from' 或 'to'）
                    """
                    field_value = target_dict.get(address_key)
                    addr_str = get_address_from_field(field_value)
                    
                    # 如果地址在标签数据中，添加标签信息
                    if addr_str and addr_str.lower() in arkham_data:
                        # 如果地址是字符串格式，先转换为字典格式
                        if isinstance(field_value, str):
                            target_dict[address_key] = {"address": field_value}
                        
                        # 添加地址信息（如果还没有添加过）
                        if "addressInfo" not in target_dict[address_key]:
                             target_dict[address_key]['addressInfo'] = arkham_data[addr_str.lower()]
                
                for tx in processed_data:
                    # 为主交易的from/to添加标签
                    enrich_address_field(tx, 'from')
                    enrich_address_field(tx, 'to')
                    # 为内部交易的from/to添加标签
                    for itx in tx.get('internalTransactions', []):
                        enrich_address_field(itx, 'from')
                        enrich_address_field(itx, 'to')
                    # 为代币转账的from/to添加标签
                    for ttx in tx.get('tokenTransfers', []):
                        enrich_address_field(ttx, 'from')
                        enrich_address_field(ttx, 'to')

                # --- 步骤 4: AI 分析 ---
                progress_bar.progress(70, text="🤖 AI 侦探正在分析每一笔交易 (Analysis by Gemini 3)...")
                
                # 检查哪些交易已经有AI分析结果（从数据库缓存中）
                txs_to_analyze = []
                for tx_hash, tx_data in processed_data_map.items():
                    if tx_hash in cached_data and cached_data[tx_hash].get('analysis'):
                        # 如果已有分析结果，直接使用缓存
                        tx_data['ai_analysis'] = cached_data[tx_hash]['analysis']
                    else:
                        # 如果没有分析结果，加入待分析列表
                        txs_to_analyze.append(tx_data)
                
                st.write(f"AI分析缓存检查：{len(processed_data) - len(txs_to_analyze)} 条已有分析，{len(txs_to_analyze)} 条需要进行AI分析。")
                
                # 如果有需要分析的交易，使用线程池并行处理
                if txs_to_analyze:
                    ai_ph = st.empty()
                    completed_count = 0
                    # 创建线程池，最多10个并发线程（与 core_logic.py 保持一致）
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        future_to_tx = {executor.submit(analyze_transaction, tx): tx for tx in txs_to_analyze}
                        for future in as_completed(future_to_tx):
                            tx = future_to_tx[future]
                            try:
                                # 获取AI分析结果（这里会等待任务完成）
                                ai_result = future.result()
                                analysis_text = ai_result.get('analysis', 'Analysis not available.')
                                # 将分析结果添加到交易数据中
                                tx['ai_analysis'] = analysis_text
                                # 保存分析结果到数据库，供下次使用
                                update_ai_analysis(tx['txhash'], analysis_text)
                            except Exception as exc:
                                # 如果某笔交易的AI分析失败，记录错误但继续处理其他交易
                                st.warning(f"交易 {tx.get('txhash')} 在AI分析环节产生错误: {exc}")
                                tx['ai_analysis'] = f'Failed to analyze: {str(exc)}'
                            
                            completed_count += 1
                            ai_ph.write(f"AI 分析进度: {completed_count}/{len(txs_to_analyze)}")
                    ai_ph.empty()
                
                st.session_state.processed_txs = list(processed_data_map.values())

                # --- 步骤 5: 生成总结 ---
                progress_bar.progress(90, text="📝 正在撰写最终侦查报告...")
                # 提取所有有效的AI分析文本（与 core_logic.py 保持一致，使用 processed_data_map）
                all_analyses = [tx.get('ai_analysis', '') for tx in processed_data_map.values() if tx.get('ai_analysis')]
                
                # 创建专门的总结生成loading区域
                summary_loading = st.empty()
                with summary_loading.container():
                    st.markdown("---")
                    st.info("""
                    **🤖 AI 侦探正在深度思考中 (Analysis by Gemini 3)......**
                    
                    **正在执行的任务：**
                    - 📊 汇总所有交易行为模式
                    - 🎯 推断用户身份与策略  
                    - 💰 分析资金流向图谱
                    - ⚠️ 评估潜在风险点
                    
                    *Gemini 3 Pro 正在生成深度画像报告，这可能需要 10-30 秒，请稍候...*
                    """)
                
                # 调用AI生成报告（这个过程可能需要10-30秒）
                # 使用spinner包裹，让用户知道程序没有卡死
                with st.spinner("🕵️‍♂️ AI 正在分析链上数据，生成深度画像报告..."):
                    final_report = generate_conclusion(target_address, all_analyses)
                
                # 生成完成后，清空loading提示
                summary_loading.empty()
                
                # 保存上下文（与 core_logic.py 保持一致，使用分隔符连接）
                analyses_summary_str = "\n\n---\n\n".join(all_analyses)
                save_chat_context(target_address, final_report, analyses_summary_str)
                
                # 保存状态
                st.session_state.report_content = final_report
                st.session_state.analyses_summary = analyses_summary_str
                st.session_state.analysis_done = True
                st.session_state.current_address = target_address
                st.session_state.messages = [{"role": "assistant", "content": "🕵️‍♂️ 报告已生成！关于这位用户的行为、动机或风险，您有什么想问的吗？"}]
                
                progress_bar.progress(100, text="分析完成！")
                time.sleep(1)
                status_container.empty()
                st.rerun()
                
            except Exception as e:
                st.error(f"分析过程中发生错误: {str(e)}")
                st.exception(e)

# ========== 结果展示区 (分析完成后显示) ==========
if st.session_state.analysis_done:
    
    # 1. 报告区域
    with st.expander("📝 深度画像报告 (点击收起)", expanded=True):
        st.markdown('<div class="highlight-box">💡 <b>AI 核心发现</b>：以下是基于链上行为生成的深度画像。</div>', unsafe_allow_html=True)
        st.markdown(st.session_state.report_content)
    
    # 2. 聊天区域
    st.divider()
    st.subheader("💬 链上侦探助手")
    st.caption("您可以像聊天一样追问更多细节，例如：“他最近一笔大额交易是在做什么？”")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("问我任何问题..."):
        from db_manager import save_chat_message
        save_chat_message(st.session_state.current_address, 'user', prompt)
        
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("🤔 正在检索链上证据...")
            
            try:
                response = chat_with_report(
                    st.session_state.current_address,
                    st.session_state.report_content,
                    st.session_state.analyses_summary,
                    [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]],
                    prompt
                )
                message_placeholder.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                save_chat_message(st.session_state.current_address, 'assistant', response)
                
            except Exception as e:
                error_msg = f"对话出错: {str(e)}"
                message_placeholder.error(error_msg)

    # 3. 原始数据区域
    st.divider()
    if st.session_state.processed_txs:
        with st.expander("📊 查看原始交易数据 (点击展开)"):
            st.caption("这里展示了所有用于分析的原始交易记录。")
            
            simple_data = []
            for tx in st.session_state.processed_txs:
                simple_data.append({
                    "时间": tx.get('time'),
                    "Hash": tx.get('txhash'),
                    "类型": "用户发起" if tx.get('isUserInitiated') else "被动交互",
                    "AI摘要": tx.get('ai_analysis', '')[:50] + "..." if tx.get('ai_analysis') else "无"
                })
            df = pd.DataFrame(simple_data)
            st.dataframe(df, use_container_width=True)
            
            st.markdown("#### 🔍 逐笔交易 JSON 详情")
            for tx in st.session_state.processed_txs:
                tx_title = f"{tx.get('time')} | {tx.get('txhash')[:8]}... | {tx.get('ai_analysis', '')[:20]}..."
                with st.expander(tx_title):
                    st.json(tx)
                    if tx.get('ai_analysis'):
                        st.info(f"**AI 完整分析:**\n\n{tx['ai_analysis']}")
    else:
        with st.expander("📊 原始交易数据"):
            st.caption("⚠️ 注意：从历史档案恢复时，暂不展示原始交易详情，仅保留分析报告和 AI 摘要。")
