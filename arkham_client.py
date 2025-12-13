"""
文件名称: arkham_client.py
文件用途: Arkham Intelligence API客户端模块，负责获取地址的标签和身份信息

主要功能:
    get_arkham_intelligence(): 批量获取地址的标签信息
    - 通过Apify平台调用Arkham Intelligence的爬虫Actor
    - 返回地址的名称、类型、标签等信息
    - 帮助AI更好地理解地址的身份（例如：CEX、DeFi协议、知名项目等）

Arkham Intelligence说明:
    Arkham Intelligence是一个区块链数据分析平台，提供地址标签和身份识别服务。
    它可以帮助识别：
    - CEX地址（交易所钱包）
    - DeFi协议地址（Uniswap、Aave等）
    - 知名项目地址
    - 个人或机构标签
    - 其他链上实体信息

Apify平台说明:
    Apify是一个Web爬虫和自动化平台，提供了Arkham Intelligence的爬虫Actor。
    我们通过Apify API调用这个Actor来获取地址标签，而不是直接调用Arkham API。

API认证:
    - 使用Apify API Token进行认证
    - Actor ID: BFRkJAsA9XBVgzoce（Arkham Scraper的固定ID）

数据格式:
    返回的标签数据包含：
    - name: 地址的名称（例如："Binance"）
    - type: 地址类型（例如："Exchange"）
    - tags: 标签列表（例如：["CEX", "Exchange"]）

性能优化:
    - 支持批量查询，一次可以查询多个地址
    - 使用代理配置（useApifyProxy）提高成功率

错误处理:
    - 如果API调用失败，返回空字典
    - 打印错误信息，但不中断程序流程

依赖库:
    - apify_client: Apify平台的Python客户端库

作者: AI链上分析器开发团队
创建日期: 2025-11-01
"""

import json
from apify_client import ApifyClient

# ========== Apify配置信息 ==========
# Apify API Token（用于认证）
APIFY_API_TOKEN = "apify_api_HFAfjh9nvVIvg8fFweVvn9c0CCcmwe1v2IZb"
# Arkham Scraper Actor的ID（固定值）
ARKHAM_ACTOR_ID = "BFRkJAsA9XBVgzoce"

# 创建Apify客户端实例
client = ApifyClient(APIFY_API_TOKEN)

def get_arkham_intelligence(wallet_addresses: list) -> dict:
    """
    调用 Apify 上的 Arkham Scraper Actor 来获取地址的 Intelligence Data。
    
    这个函数通过Apify平台调用Arkham Intelligence的爬虫，批量获取地址标签。
    标签信息可以帮助AI更好地理解地址的身份和用途。
    
    参数:
        wallet_addresses: 一个包含多个钱包地址字符串的列表
                         例如：["0x1234...", "0x5678..."]
    
    返回:
        一个字典，键是地址（小写），值是该地址的标签信息字典，包含：
        - name: 地址名称（例如："Binance"）
        - type: 地址类型（例如："Exchange"）
        - tags: 标签列表（例如：["CEX", "Exchange"]）
        
        如果API调用失败或没有找到标签，返回空字典 {}
    
    处理流程:
        1. 准备Actor输入参数（地址列表、数据类型、代理配置）
        2. 调用Actor并等待完成
        3. 从Actor返回的数据集中提取标签信息
        4. 精简数据，只保留name、type、tags字段
        5. 过滤掉完全没有信息的条目
        6. 返回地址到标签的映射字典
    
    数据精简说明:
        - 只保留name、type、tags三个字段，忽略其他冗余信息
        - 如果地址没有标签信息，不会包含在返回结果中
        - 地址统一转换为小写，便于后续查找
    
    示例:
        >>> addresses = ["0x1234...", "0x5678..."]
        >>> labels = get_arkham_intelligence(addresses)
        >>> print(labels["0x1234..."]["name"])  # 打印地址名称
    """
    # 如果地址列表为空，直接返回空字典
    if not wallet_addresses:
        return {}

    print(f"正在通过Apify Arkham Scraper分析 {len(wallet_addresses)} 个地址...")

    # ========== 准备 Actor 输入参数 ==========
    # Actor需要的输入参数：
    # - walletAddresses: 要查询的地址列表
    # - dataType: 数据类型，固定为"intelligence"（获取标签信息）
    # - proxyConfiguration: 代理配置，使用Apify的代理提高成功率
    run_input = {
        "walletAddresses": wallet_addresses,
        "dataType": "intelligence",
        "proxyConfiguration": {"useApifyProxy": True},
    }

    try:
        # ========== 运行 Actor 并等待完成 ==========
        # 调用Actor，这会启动一个爬虫任务
        # Actor会访问Arkham Intelligence网站，查询每个地址的标签信息
        # 这个过程可能需要一些时间，所以会等待完成
        run = client.actor(ARKHAM_ACTOR_ID).call(run_input=run_input)
        print("Arkham Scraper 运行完成。正在获取结果...")

        # ========== 处理并返回结果 ==========
        # Actor完成后，结果会保存在一个数据集中
        # 我们需要遍历数据集中的所有条目，提取标签信息
        address_intelligence_map = {}
        
        # 获取Actor返回的数据集，并遍历所有条目
        dataset_items = client.dataset(run["defaultDatasetId"]).iterate_items()
        
        for item in dataset_items:
            # Actor返回的数据是按链组织的（每个链一个键）
            # 我们需要遍历所有链的数据
            for chain_data in item.values():
                # 检查是否是有效的链数据（包含address字段）
                if isinstance(chain_data, dict) and "address" in chain_data:
                    # 提取地址（统一转换为小写，便于后续查找）
                    address = chain_data["address"].lower()
                    
                    # ========== 精简标签信息 ==========
                    # 从原始数据中提取关键信息
                    # entity: Arkham实体信息（如果有）
                    # label: Arkham标签信息（如果有）
                    entity = chain_data.get("arkhamEntity")
                    label = chain_data.get("arkhamLabel")
                    
                    # 构建精简的标签信息字典
                    # 只保留name、type、tags三个字段
                    intelligence_summary = {
                        "name": entity.get("name") if entity else (label.get("name") if label else None),
                        "type": entity.get("type") if entity else None,
                        # tags来自populatedTags字段，提取每个tag的label
                        "tags": [tag.get("label") for tag in chain_data.get("populatedTags", [])]
                    }
                    
                    # ========== 过滤无效条目 ==========
                    # 只保留有实际信息的条目（至少要有name或tags）
                    # 这样可以避免保存空数据
                    if intelligence_summary["name"] or intelligence_summary["tags"]:
                        address_intelligence_map[address] = intelligence_summary
        
        print(f"成功获取了 {len(address_intelligence_map)} 个地址的Arkham intelligence数据。")
        return address_intelligence_map

    except Exception as e:
        # 如果API调用失败，打印错误信息并返回空字典
        # 这样不会中断整个分析流程
        print(f"调用Apify Arkham Scraper失败: {e}")
        return {}
