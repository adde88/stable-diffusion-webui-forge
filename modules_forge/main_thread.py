# This file is the main thread that handles all gradio calls for major t2i or i2i processing.
# Other gradio calls (like those from extensions) are not influenced.
# By using one single thread to process all major calls, model moving is significantly faster.
# Optimized: Replaced time.sleep() polling with queue.Queue and threading.Event for zero-overhead blocking.

import traceback
import threading
import queue

task_queue = queue.Queue()
tasks_dict = {}
dict_lock = threading.Lock()
id_lock = threading.Lock()
last_id = 0
last_exception = None

class Task:
    def __init__(self, task_id, func, args, kwargs):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.exception = None
        # Event allows threads to wait for this specific task efficiently without CPU overhead
        self.done_event = threading.Event()

    def work(self):
        global last_exception
        try:
            self.result = self.func(*self.args, **self.kwargs)
            self.exception = None
            last_exception = None
        except Exception as e:
            traceback.print_exc()
            print(e)
            self.exception = e
            last_exception = e
        finally:
            # Signal that the task is finished, waking up any waiting threads instantly
            self.done_event.set()

def loop():
    while True:
        # get() blocks efficiently until an item is available. No time.sleep() needed.
        task = task_queue.get()
        if task is None:
            break  # Poison pill for graceful shutdown if ever needed
        
        task.work()
        task_queue.task_done()

def async_run(func, *args, **kwargs):
    global last_id
    with id_lock:
        last_id += 1
        current_id = last_id
        
    new_task = Task(task_id=current_id, func=func, args=args, kwargs=kwargs)
    
    with dict_lock:
        tasks_dict[current_id] = new_task
        
    task_queue.put(new_task)
    return current_id

def run_and_wait_result(func, *args, **kwargs):
    current_id = async_run(func, *args, **kwargs)
    
    with dict_lock:
        task = tasks_dict[current_id]
        
    # Wait efficiently until the work() method calls done_event.set()
    task.done_event.wait()
    
    with dict_lock:
        # Clean up the completed task from memory
        del tasks_dict[current_id]
        
    return task.result
