<img width="367" height="63" alt="image" src="https://github.com/user-attachments/assets/85471c8e-76c1-4c57-acf0-189282db8f30" />
<br />
<br />

Memalot finds [memory leaks](#definition-of-a-leak) in Python programs. Memalot prints suspected leaks to the console by default, and also has a [CLI](#cli) and an [MCP server](#mcp-server) for analyzing memory leaks.  

For example, here is a Python program which creates a string object every half second:

```python
from time import sleep
import memalot

memalot.start_leak_monitoring(max_object_lifetime=1.0)

def my_function():
    my_list = []
    for i in range(100000):
        my_list.append(f"Object {i}")
        sleep(0.5)

my_function()
```

The `max_object_lifetime` parameter means that Memalot will find objects that have lived for longer than one second. After a short delay, Memalot will print a report like this to the comnole:

<img width="541" height="584" alt="image" src="https://github.com/user-attachments/assets/ca07a085-aaee-4332-96bf-6a43d98fa161" />

**Note**: memalot may slow down your program, so be wary of using it in a production system.

## Installation

Install using pip:

```bash
pip3 install memalot
```

## Getting Started

Memalot can identify suspected memory leaks in one of these ways:

- [Time-based Leak Discovery](#time-based-leak-discovery). Identifies objects that have lived for more than a certain amount of time without being garbage collected. This is most suitable for web servers and other programs that process short-lived requests, and multithreaded programs. 
- [Function-based Leak Discovery](#iteration-based-leak-discovery). Identifies objects that have been created while a specific function is being called, but have not yet been garbage collected. This is most suitable for single-threaded batch processing systems or other long-lived jobs.

### Time-based Leak Discovery

To get started with time-based leak discovery, call this code after your Python program starts:

```python
import memalot

memalot.start_leak_monitoring(max_object_lifetime=60.0)
```

This will periodically print out potential memory leaks to the console. An object is considered a potential leak if it lives for more than `max_object_lifetime` seconds (in this case, 60 seconds).

### Function-based Leak Discovery

To get started with function-based leak discovery, wrap your code in the `@leak_monitor` decorator:

```python
from memalot import leak_monitor

@leak_monitor
def function_that_leaks_memory():
    # Code that leaks memory here
```

In this case, when the function exits, Memalot will print out potential memory leaks. That is, objects created while the function was being called, which cannot be garbage collected.

You can also ask Memalot to only consider objects that have lived for more than a certain number of calls to the function. For example: 

```python
from memalot import leak_monitor

@leak_monitor
def function_that_leaks_memory(max_object_age_calls=2):
    # Code that leaks memory here
```

In this case the `max_object_age_calls=2` parameter asks Memalot to only consider _objects that have been created while the function was being called, and have survived two calls to the function_. 

Note: you should *not* call `memalot.start_leak_monitoring` when using function-based leak discovery.

Note: function-based leak discovery will not work well if other threads are creating objects outside the function while it is being called. Use [time-based Leak Discovery](#time-based-leak-discovery) in this case.

## CLI

## MCP Server

## Definition of a Leak

Memalot defines a memory leak as _an object that has lived for longer than is necessary_.

However, note that Memalot cannot distinguish between objects that live for a long time when this is _necessary_ (for example, you want to cache some objects for speed) and when this is _unnecessary_ (for example, you forget to evict stale objects from your cache). It's up to you to make this distinction.

## Limitations

- Memalot is slow. Be wary of using it in a production system.
- Memalot does not guarantee to find *all* leaking objects. If you have leaking objects that are
  created very rarely, Memalot may not detect them. Specifically:
  - Memalot does not find objects that are created while the leak report is being generated. This is mostly applicable to time-based leak discovery.
  - If the `max_object_age_calls` parameter is set to greater than 1 during function-based leak discovery, Memalot will not find objects that are created on some calls to the function.
