index=0
class tree:
    def __init__(self, data):
        self.data = data
        self.left = None
        self.right = None
        self.height=0
def len_tree(node):
    if node ==None:
        return 0
    else:
        if node.left==None and node.right==None:
            return 1
        else:
            return max(len_tree(node.left),len_tree(node.right))+1
def make_tree(node:tree,data:list):
    global index
    if data[index]=="#":
        index+=1
        return None
    new_node=tree(data[index])
    index+=1
    node.left=make_tree(new_node,data,index)
    node.right=make_tree(new_node,data,index)
    return node
def print_tree(node:tree):
    print(node.data)
    print_tree(node.left)
    print_tree(node.right)
def search_node_in_tree(node:tree, data):
    if node is None:
        return "no"
    if node.data == data:
        return "yes"
    left_res = search_node_in_tree(node.left, data)
    if left_res == "yes":
        return "yes"
    right_res = search_node_in_tree(node.right, data)
    return right_res
import asyncio 
import asyncio

async def say_after(text, delay):
    await asyncio.sleep(delay)
    print(text)

async def main():
    # 创建两个任务，立刻并发
    t1 = asyncio.create_task(say_after("A", 2))
    t2 = asyncio.create_task(say_after("B", 1))

    await t1
    await t2

if __name__ == "__main__":
    asyncio.run(main())