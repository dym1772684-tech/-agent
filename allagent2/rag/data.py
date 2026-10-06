from pymilvus import MilvusClient, DataType
# 1. 初始化本地MilvusLite客户端
client = MilvusClient("./milvus_demo.db")
coll_name = "docs"
# ====================== 1. 集合管理 ======================
# 如果旧集合存在就删除，保证每次从头复现（测试用，生产去掉）
if client.has_collection(coll_name):
    client.drop_collection(coll_name)
    print("[1] 旧集合已删除\n")
# 定义Schema：auto_id=False，手动维护主键id，更适合RAG调试
schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
schema.add_field("id", DataType.INT64, is_primary=True)
schema.add_field("vector", DataType.FLOAT_VECTOR, dim=768)
schema.add_field("text", DataType.VARCHAR, max_length=65535)

# ========== 删除全部index_params相关代码！==========
# # 索引配置 HNSW
# index_params = client.prepare_index_params()
# index_params.add_index(
#     field_name="vector",
#     index_type="AUTOINDEX",
#     metric_type="COSINE",
#     params={"M": 16, "efConstruction": 200}
# )

# 创建集合，**不再传入index_params，默认FLAT暴力检索**
client.create_collection(
    collection_name=coll_name,
    schema=schema
    # index_params=index_params 删掉这一行
)
print("[1] 创建集合完成")
print("集合是否存在：", client.has_collection(coll_name))
print("集合信息：", client.describe_collection(coll_name), "\n")
# ====================== 2. 插入数据 insert ======================
data = [
    {"id": 1, "vector": [0.1] * 768, "text": "Milvus 是向量数据库"},
    {"id": 2, "vector": [0.2] * 768, "text": "支持十亿级向量检索"},
    {"id": 3, "vector": [0.3] * 768, "text": "RAG应用常用向量数据库"},
]
insert_res = client.insert(collection_name=coll_name, data=data)
print("[2] insert插入结果：", insert_res)
print("当前集合行数：", client.get_collection_stats(coll_name)["row_count"], "\n")
# ====================== 3. upsert（存在更新，不存在新增） ======================
upsert_data = [
    {"id": 2, "vector": [0.22] * 768, "text": "【更新】Milvus支持十亿级向量检索"},  # id=2存在，更新
    {"id": 4, "vector": [0.4] * 768, "text": "新增文档：向量数据库适合知识库"},      # id=4不存在，新增
]
upsert_res = client.upsert(collection_name=coll_name, data=upsert_data)
print("[3] upsert结果：", upsert_res)
print("upsert后行数：", client.get_collection_stats(coll_name)["row_count"], "\n")
# ====================== 4. query 标量查询（按字段过滤，不做向量相似度） ======================
# 查询 id >= 2 的记录
query_res = client.query(
    collection_name=coll_name,
    filter="id >= 2",
    output_fields=["id", "text"],
    limit=100
)
print("[4] query标量查询结果：", query_res, "\n")
# ====================== 5. search 向量相似度检索（核心RAG接口） ======================
query_vector = [0.11] * 768
search_res = client.search(
    collection_name=coll_name,
    data=[query_vector],
    limit=3,
    output_fields=["id", "text"],
    search_params={"metric_type": "COSINE"}
)
print("[5] 向量search检索结果：", search_res, "\n")
# search + 标量混合过滤：向量检索同时加条件
search_filter_res = client.search(
    collection_name=coll_name,
    data=[query_vector],
    filter="id > 1",
    limit=3,
    output_fields=["id", "text"]
)
print("[5.1] search+标量过滤结果：", search_filter_res, "\n")
# ====================== 6. delete 删除数据，filter表达式 ======================
del_res = client.delete(
    collection_name=coll_name,
    filter="id in [3,4]"
)
print("[6] delete删除id3、4，返回删除主键：", del_res)
print("删除后行数：", client.get_collection_stats(coll_name)["row_count"], "\n")
# ====================== 7. 分区 Partition 操作 ======================
# 创建分区
client.create_partition(collection_name=coll_name, partition_name="tech")
print("[7] 创建分区 tech")
# 插入数据到指定分区
partition_data = [{"id": 10, "vector": [0.5]*768, "text":"分区内文档：RAG+Agent开发"}]
client.insert(collection_name=coll_name, data=partition_data, partition_name="tech")
# 只在tech分区检索
partition_search = client.search(
    collection_name=coll_name,
    data=[[0.51]*768],
    partition_names=["tech"],
    limit=5,
    output_fields=["id", "text"]
)
print("[7.1] 在tech分区检索结果：", partition_search)
# 删除分区（删除前分区数据会被清理）
client.drop_partition(collection_name=coll_name, partition_name="tech")
print("[7.2] 删除分区tech完成\n")
# ====================== 8. 索引相关操作（演示单独建索引，前面创建集合已经自动建了，这里仅演示API） ======================
# 【测试】如果想手动单独创建索引，要先删掉原有索引
# client.drop_index(collection_name=coll_name, index_name="vector_index")
# new_index_params = client.prepare_index_params()
# new_index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
# client.create_index(collection_name=coll_name, index_params=new_index_params)
# print("[8] 重建索引完成\n")
# ====================== 9. 集合统计、加载/释放（MilvusLite加载基本透明，服务端Milvus必用） ======================
stats = client.get_collection_stats(coll_name)
print("[9] 集合统计信息：", stats)
# client.load_collection(coll_name)
# client.release_collection(coll_name)

# =========== 新增：强制刷盘，持久化原始向量数据到磁盘 ===========
client.flush(collection_name=coll_name)
print("[FINAL] flush执行完成，数据写入磁盘")

# ====================== 10. 删除集合（收尾，可注释保留库） ======================
# client.drop_collection(coll_name)
# print("[10] 集合已删除，清理完毕")
