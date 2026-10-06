import json
import zstandard

file_path = r"C:\Users\17726\.dsh\sessions\--C-Users-17726-deepseek-harness--\session-063a046f-96da-489b-994a-b11ab7a5199b\session.jsonl.zstd"

dctx = zstandard.ZstdDecompressor()
with open(file_path, "rb") as f:
    with dctx.stream_reader(f) as reader:
        buffer = b""
        while chunk := reader.read(16384):
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                obj = json.loads(line.decode("utf-8"))
                # 打印事件，或者过滤 claim / queued prompt
                print(obj)
