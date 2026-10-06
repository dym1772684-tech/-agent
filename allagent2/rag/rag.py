import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
from collections import defaultdict
from typing import List
import math
import jieba
from typing import Dict,Any
from collections import defaultdict
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer
from typing import List
import chromadb
def fenci(chunks: List[str]):
    # 使用列表推导式会更简洁
    return [jieba.lcut(chunk) for chunk in chunks]
def TF(doc_words: List[str]):
    """统计单篇文档(已分词)里每个词出现的次数"""
    tf_dict = {}
    for word in doc_words:
        tf_dict[word] = tf_dict.get(word, 0) + 1
    return tf_dict
def query_list(words: List[str]):
    # 创建一个字典，统计每个词出现的次数，初始值为0
    k = {}
    for word in words:
        k[word] = 0
    return k

def check_grade(chunks: List[str], query: List[str]):
    words_list = fenci(chunks)  # 得到每个片段分词后的列表
    results = []  # 初始化为空列表
    stopwords = {"的", "是", "在", "有", "和"}
    for i in range(len(words_list)):
        # 为当前片段创建一个统计字典
        fragment_dict = query_list(words_list[i])
        
        # 统计分词后的词在 query 中出现的次数
        for word in words_list[i]:
            if word in query and word not in stopwords:
                fragment_dict[word] += 1
        
        results.append(fragment_dict)
    
    return results
def calculate_keyword_score(results_dicts: List[Dict[str, int]]) -> List[float]:
    """将词频统计转化为简单的分值（如：所有匹配词的频数之和）"""
    scores = []
    for d in results_dicts:
        # 计算该片段中，所有关键词出现的总次数作为分数
        score = sum(d.values())
        scores.append(float(score))
    return scores

def embed_chunk(chunk:str,embedding_model)->List[float]:
    embedding=embedding_model.encode(
        chunk,
        batch_size=32,#控制解析并发度
        normalize_embeddings=True,
        show_progress_bar=True
        )
    return embedding.tolist()
def split_into_chunks(doc_file:str)->List[str]:
    info_path=os.path.join(os.path.dirname(__file__),"information.md")
    with open(info_path,"r",encoding="utf-8") as file:
        content=file.read()
        return [chunk for chunk in content.split("\n\n")]
def save_embeddings(chunks:list[str],embeddings:List[List[float]],collection:chromadb.Collection)->None:
    ids=[str(i) for i in range(len(chunks))]    
    collection.add(
        documents=chunks,#所有的内容片段
        embeddings=embeddings,#切分向量,就相当于把对应的内容 和对应的切分向量直接存进去 不用chromdb本身的向量切分
        ids=ids#id
    )
def avg_doc_len(fenci_result: List[List[str]]):
    total_len = sum(len(doc_words) for doc_words in fenci_result)
    return total_len / len(fenci_result)            
 
def BM_25(quer_words: List[str],fenci_result: List[List[str]],chunks:List[str],k1=1.5,b=0.75):
    N = len(fenci_result)
    df_dict = DF(fenci_result)
    idf_dict = IDF(
        df_dict,
        N
    )
    avgdl = avg_doc_len(
        fenci_result
    )
    results=[]
    for index,doc_words in enumerate(fenci_result):
        doc_len=len(doc_words)
        tf_dict=TF(doc_words)
        score=0.0
        for word in quer_words:
            if word not in tf_dict:
                continue
            idf=idf_dict.get(
                word,
                0
            )
            tf=tf_dict[word]
            numerator=tf*(k1+1)
            denominator=(
                tf+k1*(1-b+b*doc_len/avgdl)
                )
            score += (idf*numerator/denominator)
        results.append(
            {
                "id":str(index),
                "text":chunks[index],
                "score":score
            }
        )


    return results

def DF(fenci: List[List[str]]):
    df_dict = defaultdict(int)
    # 遍历每一篇文档
    for doc_words in fenci:
        # 本篇文档去重，同一个词只保留一份
        unique_word = set(doc_words)
        # 本篇出现过的所有词，DF全部+1
        for w in unique_word:
            df_dict[w] += 1
    return dict(df_dict)#常用对象的api要学习一下
def IDF(df_dict:dict, N:int):

    idf_dict={}

    for word,df in df_dict.items():

        idf_dict[word]=math.log(
            (N-df+0.5)
            /
            (df+0.5)
            +1
        )

    return idf_dict

# #####召回
def vector_retrieve(query:str,top_k,embedding_model,collection):
    if collection is None:
        return []
    if embedding_model is None or not hasattr(embedding_model, "encode"):
        return []

    try:
        query_embedding = embed_chunk(query, embedding_model)
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    except Exception:
        return []

    output=[]

    for i in range(len(results["ids"][0])):

        output.append(
            {
            "id":results["ids"][0][i],

            "text":results["documents"][0][i],

            "distance":results["distances"][0][i]

            }
        )

    return output###这种方式是向量库自己的检索 我就是需要在这里进行改造
from sentence_transformers import CrossEncoder
from typing import List, Dict, Any


# 模型只加载一次
# 【优化】CrossEncoder 加载较重，原实现每次 rerank 都重新加载一次；
# 改为模块级惰性单例，整个进程只加载一次，排序逻辑与结果完全不变。
_cross_encoder=None
def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder=CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
    return _cross_encoder

def rerank(
    query: str,
    rrf_result: List[Dict[str, Any]],
    top_k: int = 5
):
    """
    接收RRF融合后的结果
    使用CrossEncoder重新排序

    参数:
        query:
            用户问题

        rrf_result:
            RRF返回结果

            [
                {
                    "id":"1",
                    "text":"xxx",
                    "score":0.03
                }
            ]

        top_k:
            最终保留数量

    返回:
        rerank后的文档列表
    """
    cross_encoder = _get_cross_encoder()  # 【优化】复用单例，不再每次加载模型
    # 【优化】CrossEncoder 构造参数已移除，统一走 _get_cross_encoder() 单例


    # 取出文本
    documents = [
        item["text"]
        for item in rrf_result
    ]


    # CrossEncoder需要(query, document)
    pairs = [
        (query, doc)
        for doc in documents
    ]


    # 计算相关性分数
    scores = cross_encoder.predict(
        pairs
    )


    # 重新组合
    rerank_result=[]


    for item,score in zip(
        rrf_result,
        scores
    ):

        rerank_result.append(
            {
                "id":item["id"],
                "text":item["text"],
                "rrf_score":item["score"],
                "rerank_score":float(score)
            }
        )


    # 按rerank分数排序
    rerank_result.sort(
        key=lambda x:x["rerank_score"],
        reverse=True
    )


    return rerank_result[:top_k]
def rrf_fusion(
    bm25_result,
    vector_result,
    k=60
):

    scores={}

    documents={}


    # BM25排名贡献

    for rank,item in enumerate(bm25_result):

        doc_id=item["id"]


        scores[doc_id]=scores.get(doc_id,0)+(
            1/(k+rank+1)
        )


        documents[doc_id]=item["text"]



    # Vector排名贡献

    for rank,item in enumerate(vector_result):

        doc_id=item["id"]


        scores[doc_id]=scores.get(doc_id,0)+(
            1/(k+rank+1)
        )


        documents[doc_id]=item["text"]



    # 排序

    result=[]


    for doc_id,score in scores.items():

        result.append(
            {
                "id":doc_id,
                "text":documents[doc_id],
                "score":score
            }
        )


    result.sort(
        key=lambda x:x["score"],
        reverse=True
    )


    return result
"""提示词 检索其 数据库 得到文件 融入信息 得到结论
文档加载→清洗→切块→Embedding→向量入库→多路召回→Rerank→Prompt 编排→LLM 生成
神经网路 存储 词汇之间相互搭配出现的概率，捕获在上下文的意义，首先生成已有词汇的句子含义
然后遍历词汇 ，标记下个词的出现概率 自回归性 随机性
普通数据库 向量数据库
"""


"""关键词检索   附着元数据metdate 用来缩小寻找文档的范围
共同词汇： 根据用户提出的话语 只关心出现了哪些词语，其他词语都是 只加一次分，
自己选定的关键词多次加分，总词数除以总分就可以得到归一化，为词语加权：IDF，先算某一个词语在
所有文档中的频率，然后再取倒数，得到稀缺性，再取对数

BM25 计算公式 
语义检索 将文本和提示词生成向量模型 embedding 
计算向量的 相似度 就是 距离 和余弦角度 点积 投影长度

现在有种方法 就是 通过两种方式排序 然后 使用rank方式 来加权相加



测试方法 ，准确率（所需文档数字）和 召回率（ 相关文档数字）

临近图选择算法

HNSW算法

向量数据库


分块技术：重叠分块，语义分块，给大模型分块


检索优化：通过llm本身根据用户提示词 加强适合检索的内容，优化检索，其他算法

双编码器：biencoder、 速度快
交叉编码器：把文档和提示词 交叉到一起 然后交叉编码器就可以直接输出匹配度 质量高
colbert

重排：用更强的模型去算小范围事情


LLM：transformer 编码器   解码器  注意力机制:token关注其他对他最大影响的 
注意力头 ：有多个 代表着每个词语与其他词语的关系





得到提示词 ，生成稀疏向量（通过词汇，来给文章打分，有词汇就加分，然后选出最高的） ，
然后会被存储到向量中  向量上的内容代表出现次数(向量的构建内容取决于询问的话语，维度维度 = 
所有文档合并后，不重复词语的总个数，文档包含这个词语（问题中的），就在对应向量处加分
我们在其中需要为稀缺词语提权，
就是用每个关键词的分数除以总词数，然后就是逆文档频率，就是用文档中出现的词语去除以文档总数，
得到他的出现频率，然后再取他们的倒数，来定义稀缺性，这就涉及到一个置换大小，然后就是log减少
具体过程如下，检索所有文档，确认不同词语个数，建立向量，然后进行TF，即将问题中的
词语 在文档中检索，出现一个，向量位置加分，同时用向量分数除以文档的总词数，这用来将长文档的
优势取代，这是TF整体过程，之后的逆文档频率在于，需要统计各种所有词语（每个词语），出现过文档的个数，除以
总文档数量，来确定这个词是否是某些文档特有的（赋权），提高准确性，最后就是取倒数，越高频率越不稀有，
然后取倒数，
语义检测
元数据过滤 通过某些关键的东西 过滤出最相关的内容（文档
然后 让检索其引用
沙箱 harness 根据问题本身确定调用模型，权限问题，上下文记忆管理，定位分项目，多模态分析
steer引导功能
语义检索 embedding
检索器 元数据筛选 关键词筛选 语义检索 
然后汇总的统计分数，,使用倒数k来运算
检索器质量：prompt本身，排序统计质量，所有相关文档
衡量标准：
准确率：召回的相关文档数量（我真正需要的部分）/总的召回文档数量    我明白我需要的数量（真正我自己定义的和问题有关的）
召回率：召回的相关文档数量（我真正需要的部分）/我明白我需要的数量（真正我自己定义的和问题有关的）
衡量标准：划定需要的文档数量，然后对他们进行准确率分析

嵌入模型：
embbing 
图
k近邻算法：找向量的距离，然后通过判断夹角，距离确定所需文档，多数据处理差
ANN    
HNSW算法：多层架构，首先是上层最少，根据条件然后寻找到某个向量，以这个向量为基础，向下层高数据继续循环
近似最近邻算法
向量数据库 weaviate 不同的向量数据库  创建数据库 录入文档 转为向量 语义搜索的的稠密嵌入向量 最近邻搜索的索引
额外措施：
分块：用于减少大模型占用，将长文本文档分为小块，对嵌入模型（大小限制），检索相关性指标，将文本中最有用的给大模型
用来让向量数据库轻松检阅
限制：切块大小，重叠 ，针对不同的文档不同的切分方式  
语境：语义分段，相近语义分段，把两个句子都转化为向量，算距离，然后找到下一个，可以基于提示词 让大语言模型进行切分，
 对于查询提示词的处理：转化 重写提示词为向量，重写查询，称为切分的一个小组件，关键词
HIDE：通过生成一个理想文档来规范需要的文档信息，生成所需的向量，然后再去对照
、交叉编码器 cross encoder：将文档与提示拼接，然后进入专用的嵌入模型，让模型更能了解关系，直接输出相关性分数 多数据很难受，质量高但是慢
双编码器速度快 提前生成向量
colbert:

transfomer架构：


chromadb
🎨 核心概念：理解Chroma的积木世界
在开始搭建前，我们先认识几个核心概念：

Collection（集合）：你可以把它想象成关系型数据库中的一张"表"，用来存放一组相关的文档。

Document（文档）：你要存储和检索的原始文本内容，比如你之前切分好的那些文学作品片段。

Embedding（向量）：文本的数学表示，计算机通过它来理解语义。

Metadata（元数据）：附加在文档上的标签（键值对），用于精确过滤结果。

ID（唯一标识）：每个文档的唯一标识符，用来更新和删除。
"""
