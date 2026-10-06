import asyncio
import time
async def user():
    print("start",time.time())
    await asyncio.sleep(1)
    print("end",time.time())

async def user2():
    print("start",time.time())
    await asyncio.sleep(0.5)
    print("end",time.time())

async def main():
    task=asyncio.create_task(user())
    task2=asyncio.create_task(user2())
    asyncio.gather(user2())
    await task
asyncio.run(main())


