import threading
import time
def test():
    print("线程1")
class MyThread(threading.Thread):
    def run(self):
        print("start")
        ###
        print("end")
thread_obj=threading.Thread(target=test,args=())
thread=MyThread()
thread.start()
thread.join()