"""
文件名称: core_logic.py
文件用途: 核心业务逻辑模块，实现完整的链上地址分析流程

主要功能:
    1. run_new_analysis(): 执行全新的地址分析流程
       - 获取交易摘要和详情
       - 数据清洗和处理
       - 获取地址标签（Arkham Intelligence）
       - AI分析每笔交易
       - 生成总结报告
       - 保存结果并启动对话会话
    
    2. restore_chat_session(): 恢复历史聊天会话
       - 从数据库加载之前的分析报告和对话历史
       - 继续之前的对话
    
    3. start_chat_session(): 管理交互式对话会话
       - 处理用户提问
       - 调用AI生成回答
       - 保存对话历史

核心流程说明:
    1. 数据获取阶段:
       - 通过OKX API获取交易摘要列表
       - 检查数据库缓存，只获取缺失的交易详情
       - 在线获取缺失的交易详情并保存到数据库
    
    2. 数据处理阶段:
       - 提取交易基本信息（哈希、时间、链ID等）
       - 清洗和格式化交易数据
       - 过滤重要的内部交易和代币转账
    
    3. 数据丰富阶段:
       - 收集所有涉及的地址
       - 从数据库或Arkham API获取地址标签
       - 将标签信息添加到交易数据中
    
    4. AI分析阶段:
       - 并行调用AI分析每笔交易（使用线程池提高效率）
       - 检查AI分析缓存，避免重复分析
       - 保存AI分析结果到数据库
    
    5. 报告生成阶段:
       - 汇总所有AI分析结果
       - 生成最终的用户画像和行为总结报告
       - 保存报告和上下文到数据库
    
    6. 对话阶段:
       - 启动交互式对话，用户可以就报告提问
       - 保存对话历史到数据库

性能优化:
    - 使用数据库缓存避免重复API调用
    - 使用线程池并行处理AI分析
    - 使用进度条显示处理进度

依赖模块:
    - okx_api_client: OKX API客户端
    - data_processor: 数据处理和清洗
    - ai_client: 单笔交易AI分析
    - arkham_client: Arkham Intelligence标签获取
    - ai_conclusion: AI总结生成和对话
    - db_manager: 数据库操作

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import json
import sys
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 项目内部模块导入
from okx_api_client import get_transactions_by_address, get_transaction_detail_by_hash
from data_processor import extract_tx_info_from_summary, process_and_clean_details
from ai_client import analyze_transaction
from arkham_client import get_arkham_intelligence
from ai_conclusion import generate_conclusion, chat_with_report
from db_manager import (
    get_transaction_details_by_hashes, add_transaction_detail, 
    get_labels_by_addresses, add_labels, update_ai_analysis,
    load_chat_session, setup_chat_database,
    save_chat_context, save_chat_message
)
# from ui import start_chat_session # 移除此行以打破循环导入

def run_new_analysis(address: str, chains: str, limit: int):
    """
    执行一次全新的地址分析流程。
    
    这是整个系统的核心函数，执行完整的分析流程：
    1. 获取交易数据（摘要+详情）
    2. 处理和数据清洗
    3. 获取地址标签
    4. AI分析
    5. 生成报告
    6. 启动对话
    
    参数:
        address: 要分析的钱包地址（例如：0x1234...）
        chains: 链ID，可以是单个链或多个链（用逗号分隔，例如："1" 或 "1,56"）
        limit: 要获取的交易数量上限
    
    流程详解:
        步骤1: 获取交易摘要列表
            - 调用OKX API获取指定地址的交易摘要
            - 提取交易哈希、链ID、时间戳等信息
            - 去重处理，确保每条交易只处理一次
        
        步骤2: 检查交易缓存
            - 从数据库查询已缓存的交易详情
            - 只对未缓存的交易进行在线获取
            - 这样可以大大减少API调用次数，提高效率
        
        步骤3: 在线获取缺失的交易详情
            - 遍历未缓存的交易，逐个调用API获取详情
            - 每次请求后休眠1.1秒，避免API限流
            - 将获取到的详情保存到数据库
        
        步骤4: 数据处理和清洗
            - 调用process_and_clean_details处理原始数据
            - 格式化时间戳、Gas费用等字段
            - 过滤重要的内部交易和代币转账
        
        步骤5: 收集地址并获取标签
            - 从所有交易中提取涉及的地址（from/to/内部交易/代币转账）
            - 检查数据库中的地址标签缓存
            - 对未缓存的地址调用Arkham API获取标签
            - 将标签信息添加到交易数据中
        
        步骤6: AI分析交易
            - 检查数据库中的AI分析缓存
            - 只对未分析的交易调用AI
            - 使用线程池并行处理，提高效率（最多10个并发）
            - 显示进度条，方便用户了解处理进度
        
        步骤7: 保存结果到JSON文件
            - 将所有处理后的交易数据保存到JSON文件
            - 文件名格式：{address}_{timestamp}.json
        
        步骤8: 生成总结报告
            - 汇总所有AI分析结果
            - 调用AI生成最终的用户画像和行为总结
            - 报告包含：用户画像、操作模式、资产偏好、行为模式等
        
        步骤9: 初始化聊天会话
            - 创建聊天数据库
            - 保存报告和分析摘要作为上下文
            - 启动交互式对话
        
    异常处理:
        - 使用try-except捕获所有异常
        - 打印错误信息到stderr
        - 确保程序不会因为单个错误而崩溃
    """
    try:
        # ========== 步骤1: 获取交易摘要列表 ==========
        # 调用OKX API获取指定地址的交易摘要
        # 返回的数据包含交易哈希、链ID、时间戳等基本信息，但不包含详细内容
        print(f"\n正在为地址 {address} 在链 {chains} 上获取最新的 {limit} 条交易摘要...")
        raw_summary_data = get_transactions_by_address(address, chains, limit)
        
        # 检查是否成功获取到数据
        if not raw_summary_data:
            print("未能获取到任何交易数据。")
            return

        # 从原始摘要数据中提取关键信息（交易哈希、链ID、时间戳）
        # 这些信息将用于后续获取交易详情
        tx_info_list = extract_tx_info_from_summary(raw_summary_data)
        if not tx_info_list:
            print("无法从摘要数据中提取交易信息。")
            return

        # 去重处理：使用set记录已见过的交易哈希
        # 因为API可能返回重复的交易，需要确保每条交易只处理一次
        unique_tx_hashes = set()
        unique_tx_info_list = []
        for tx_info in tx_info_list:
            if tx_info['txHash'] not in unique_tx_hashes:
                unique_tx_hashes.add(tx_info['txHash'])
                unique_tx_info_list.append(tx_info)
        
        tx_info_list = unique_tx_info_list

        # ========== 步骤2: 检查交易缓存 ==========
        # 从数据库中查询已缓存的交易详情，避免重复调用API
        # 这是性能优化的关键：如果之前已经分析过这个地址，可以直接使用缓存
        print("\n检查交易详情缓存...")
        hashes_to_check = [tx['txHash'] for tx in tx_info_list]
        cached_data = get_transaction_details_by_hashes(hashes_to_check)
        
        # 筛选出需要在线获取的交易（不在缓存中的）
        tx_info_to_fetch_online = [tx for tx in tx_info_list if tx['txHash'] not in cached_data]
        
        # 提取已缓存的交易详情
        cached_raw_details = [item['detail'] for item in cached_data.values()]
        print(f"共找到 {len(tx_info_list)} 条唯一交易。其中 {len(cached_raw_details)} 条已缓存，{len(tx_info_to_fetch_online)} 条需在线获取。")
        all_details_raw = cached_raw_details

        # ========== 步骤3: 在线获取缺失的交易详情 ==========
        # 只对未缓存的交易调用API，减少API调用次数
        if tx_info_to_fetch_online:
            print("\n开始在线获取缺失的交易详情...")
            for i, tx_info in enumerate(tx_info_to_fetch_online):
                print(f"正在获取第 {i+1}/{len(tx_info_to_fetch_online)} 条交易详情: {tx_info['txHash']}")
                try:
                    # 调用API获取交易详情（包含内部交易、代币转账等完整信息）
                    detail = get_transaction_detail_by_hash(tx_info['chainIndex'], tx_info['txHash'])
                    if detail:
                        # API可能返回一个列表（某些链可能返回多条记录）
                        all_details_raw.extend(detail)
                        # 将获取到的详情保存到数据库，供下次使用
                        for d in detail:
                             add_transaction_detail(d['txhash'], d['chainIndex'], address, d)
                    # 休眠1.1秒，避免API限流
                    # 这是API调用的最佳实践：在请求之间添加延迟
                    time.sleep(1.1)
                except Exception as e:
                    # 如果某条交易获取失败，打印错误但继续处理其他交易
                    # 这样可以确保部分失败不会影响整体流程
                    print(f"获取交易 {tx_info['txHash']} 详情失败: {e}")

        # ========== 步骤4: 处理数据 ==========
        # 对原始交易数据进行清洗和格式化
        # 包括：格式化时间戳、计算Gas费用、过滤重要交易、组织数据结构等
        print("\n正在处理所有详细交易数据...")
        processed_data = process_and_clean_details(all_details_raw, address)
        # 将处理后的数据转换为字典，以交易哈希为键，方便后续查找
        processed_data_map = {tx['txhash']: tx for tx in processed_data}

        # ========== 步骤5: 获取地址标签 ==========
        # 收集所有涉及的地址，并获取它们的标签信息（名称、类型、标签等）
        # 这些标签来自Arkham Intelligence，可以帮助AI更好地理解地址的身份
        
        # 辅助函数：从字段中提取地址
        # 因为地址可能以字符串或字典形式存储，需要统一处理
        all_addresses = set()
        def get_address_from_field(field_value):
            """从字段值中提取地址，支持字符串和字典两种格式"""
            if isinstance(field_value, dict):
                return field_value.get('address')
            elif isinstance(field_value, str):
                return field_value
            return None

        # 遍历所有交易，收集涉及的地址
        # 包括：主交易的from/to、内部交易的from/to、代币转账的from/to
        for tx in processed_data:
            all_addresses.add(tx['from']['address'])
            all_addresses.add(tx['to']['address'])
            # 收集内部交易中的地址
            for itx in tx.get('internalTransactions', []):
                all_addresses.add(get_address_from_field(itx.get('from')))
                all_addresses.add(get_address_from_field(itx.get('to')))
            # 收集代币转账中的地址
            for ttx in tx.get('tokenTransfers', []):
                all_addresses.add(get_address_from_field(ttx.get('from')))
                all_addresses.add(get_address_from_field(ttx.get('to')))
        # 移除空值
        all_addresses.discard(None)
        all_addresses.discard("")
        
        all_addresses_list = list(all_addresses)
        
        # 检查数据库中的地址标签缓存
        # 如果之前已经查询过这些地址，可以直接使用缓存
        print("\n检查地址标签缓存...")
        cached_labels = get_labels_by_addresses(all_addresses_list)
        print(f"找到 {len(cached_labels)} 个已缓存的地址标签。")

        # 筛选出需要在线获取标签的地址（不在缓存中的）
        addresses_to_fetch_online = [addr for addr in all_addresses_list if addr.lower() not in cached_labels]
        
        # 合并缓存和在线获取的标签
        arkham_data = cached_labels
        if addresses_to_fetch_online:
            print(f"需要为 {len(addresses_to_fetch_online)} 个新地址在线获取标签...")
            # 调用Arkham API获取地址标签（批量获取，提高效率）
            newly_fetched_labels = get_arkham_intelligence(addresses_to_fetch_online)
            
            # 将新获取的标签保存到数据库
            if newly_fetched_labels:
                add_labels(newly_fetched_labels)
                print("新获取的地址标签已存入数据库。")
            
            # 合并到总标签字典中（统一转换为小写，便于查找）
            arkham_data.update({k.lower(): v for k, v in newly_fetched_labels.items()})
        
        # ========== 步骤5.5: 丰富数据 ==========
        # 将获取到的地址标签信息添加到交易数据中
        # 这样AI分析时就能知道每个地址的身份（例如：Uniswap合约、CEX地址等）
        for tx in processed_data:
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
        
        # ========== 步骤6: AI分析 ==========
        # 对每笔交易进行AI分析，生成详细的行为解读
        # 使用缓存机制，避免重复分析相同的交易
        
        # 检查哪些交易已经有AI分析结果（从数据库缓存中）
        txs_to_analyze = []
        for tx_hash, tx_data in processed_data_map.items():
            if tx_hash in cached_data and cached_data[tx_hash].get('analysis'):
                # 如果已有分析结果，直接使用缓存
                tx_data['ai_analysis'] = cached_data[tx_hash]['analysis']
            else:
                # 如果没有分析结果，加入待分析列表
                txs_to_analyze.append(tx_data)
        
        print(f"\nAI分析缓存检查：{len(processed_data) - len(txs_to_analyze)} 条已有分析，{len(txs_to_analyze)} 条需要进行AI分析。")

        # 如果有需要分析的交易，使用线程池并行处理
        # 并行处理可以大大提高效率，因为AI API调用是I/O密集型操作
        if txs_to_analyze:
            print(f"\n开始使用AI并行分析 {len(txs_to_analyze)} 条交易...")
            # 创建线程池，最多10个并发线程
            # 注意：并发数不能太高，避免API限流
            with ThreadPoolExecutor(max_workers=10) as executor:
                # 提交所有AI分析任务到线程池
                # future_to_tx 用于跟踪每个任务对应的交易数据
                future_to_tx = {executor.submit(analyze_transaction, tx): tx for tx in txs_to_analyze}
                
                # 使用tqdm显示进度条，方便用户了解处理进度
                # as_completed会按完成顺序返回future对象，不按提交顺序
                for future in tqdm(as_completed(future_to_tx), total=len(txs_to_analyze), desc="AI分析进度"):
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
                        print(f"\n[错误] 交易 {tx.get('txhash')} 在AI分析环节产生错误: {exc}")
                        tx['ai_analysis'] = f'Failed to analyze: {str(exc)}'
        
        # ========== 步骤7: 保存JSON文件 ==========
        # 将所有处理后的交易数据保存到JSON文件，方便后续查看和调试
        output_dir = 'data/json'
        os.makedirs(output_dir, exist_ok=True)
        # 使用时间戳生成唯一的文件名，避免覆盖之前的分析结果
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{output_dir}/{address}_{timestamp_str}.json"
        
        print(f"\n正在将结果保存到文件: {output_filename}")
        # 保存为格式化的JSON，便于阅读
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(list(processed_data_map.values()), f, indent=2, ensure_ascii=False)
        
        # ========== 步骤8: 生成总结报告 ==========
        # 汇总所有单笔交易的AI分析结果，生成一份综合的用户画像和行为总结报告
        # 提取所有有效的AI分析文本
        all_ai_analyses = [tx.get('ai_analysis', '') for tx in processed_data_map.values() if tx.get('ai_analysis')]
        print("\n\n" + "="*20 + " 最终分析报告 " + "="*20)
        print(f"正在为地址 {address} 生成总结报告...")
        # 调用AI生成综合报告（包含用户画像、操作模式、资产偏好、行为模式等）
        final_report = generate_conclusion(address, all_ai_analyses)
        print(final_report)
        print("="*55)
        
        # ========== 步骤9: 初始化并保存聊天会话 ==========
        # 为后续的对话功能准备数据
        # 将所有AI分析结果合并为一个字符串，作为对话的上下文
        analyses_summary_str = "\n\n---\n\n".join(all_ai_analyses)
        # 创建或验证聊天数据库
        setup_chat_database(address)
        # 保存报告和分析摘要作为对话上下文
        # 这样在对话时，AI可以基于这些上下文回答问题
        save_chat_context(address, final_report, analyses_summary_str)
        
        # ========== 步骤10: 进入聊天 ==========
        # 启动交互式对话会话，用户可以就报告和数据提问
        start_chat_session(address, final_report, analyses_summary_str)

    except Exception as e:
        print(f"\n程序运行出错: {e}", file=sys.stderr)

def restore_chat_session(address: str):
    """
    恢复并继续一个历史聊天会话。
    
    功能说明:
        从数据库加载之前保存的分析报告、分析摘要和对话历史，
        然后继续之前的对话会话。用户可以继续提问，AI会基于历史上下文回答。
    
    参数:
        address: 要恢复的地址（用于查找对应的数据库文件）
    
    流程:
        1. 从数据库加载报告、分析摘要和历史对话记录
        2. 显示报告和历史对话（如果有）
        3. 启动新的对话会话，继续之前的对话
    
    使用场景:
        - 用户之前分析过某个地址，现在想继续提问
        - 用户想查看之前的分析结果
        - 用户想基于之前的分析继续深入讨论
    """
    print(f"\n正在加载地址 {address} 的历史记录...")
    try:
        report, analyses_summary, history = load_chat_session(address)
        print("历史记录加载成功！进入对话模式。")
        print("\n" + "="*55)
        print(report)
        print("="*55)
        
        # 如果有历史记录，打印出来
        if history:
            print("\n" + "="*20 + " 历史对话记录 " + "="*20)
            for i, msg in enumerate(history, 1):
                role_name = "您" if msg['role'] == 'user' else "AI"
                content_preview = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
                print(f"{i}. [{role_name}]: {content_preview}")
            print("="*55)
        
        start_chat_session(address, report, analyses_summary, history)
    except Exception as e:
        print(f"加载历史记录失败: {e}", file=sys.stderr)

def start_chat_session(address: str, report: str, analyses_summary: str, history: list = None):
    """
    启动并管理一个交互式聊天会话。
    
    这是对话功能的核心函数，管理用户与AI的交互。
    AI会基于报告和分析摘要回答用户的问题。
    
    参数:
        address: 当前会话的地址（用于保存对话记录）
        report: 总结报告（AI生成的综合分析报告）
        analyses_summary: 交易分析摘要（所有单笔交易的AI分析结果，用分隔符连接）
        history: 可选的已有历史记录（恢复会话时使用）
    
    对话流程:
        1. 显示提示信息，告诉用户可以开始提问
        2. 如果有历史记录，先显示之前的对话
        3. 进入循环，等待用户输入
        4. 用户输入问题后，调用AI生成回答
        5. 保存用户问题和AI回答到数据库
        6. 将对话添加到历史记录中
        7. 重复步骤3-6，直到用户输入退出命令
    
    退出命令:
        - 'exit', 'quit', '退出' - 结束对话并返回主菜单
    
    技术实现:
        - 使用chat_with_report函数调用AI API
        - 每次调用都会包含完整的上下文（报告+分析摘要+历史对话）
        - 这样可以确保AI的回答基于完整的上下文，保持对话的连贯性
    """
    # 显示对话开始提示
    print("\n" + "="*20 + " 开始对话分析 " + "="*20)
    print("您可以就以上报告和数据进行提问。输入 'exit' 或 '退出' 即可结束对话。")

    # 初始化对话历史（如果有历史记录，使用历史记录；否则使用空列表）
    chat_history = history if history is not None else []
    
    # 如果有历史记录，在开始新的对话前先显示
    # 这样用户可以回顾之前的对话内容
    if chat_history:
        print("\n" + "="*20 + " 之前的对话 " + "="*20)
        for msg in chat_history:
            # 根据角色显示不同的名称（用户显示"您"，AI显示"AI"）
            role_name = "您" if msg['role'] == 'user' else "AI"
            print(f"{role_name}: {msg['content']}")
        print("="*55 + "\n")

    # 主对话循环：持续接收用户输入并生成回答，直到用户退出
    while True:
        # 获取用户输入（去除首尾空格）
        user_query = input("您: ").strip()
        
        # 检查退出命令
        if user_query.lower() in ['exit', 'quit', '退出']:
            print("\n对话已结束。")
            break
        
        # 如果用户输入为空，跳过本次循环
        if not user_query:
            continue
        
        # 保存用户的问题到数据库
        save_chat_message(address, 'user', user_query)
        
        # 调用AI生成回答
        # AI会基于报告、分析摘要和历史对话生成回答
        ai_response = chat_with_report(
            address=address,
            report=report,
            analyses_summary=analyses_summary,
            history=chat_history,
            user_query=user_query
        )
        
        # 显示AI的回答
        print(f"AI: {ai_response}")
        
        # 将用户问题和AI回答添加到对话历史中
        # 这样后续的问题可以基于完整的对话历史回答
        chat_history.append({"role": "user", "content": user_query})
        chat_history.append({"role": "assistant", "content": ai_response})
        
        # 保存AI的回答到数据库
        save_chat_message(address, 'assistant', ai_response)
