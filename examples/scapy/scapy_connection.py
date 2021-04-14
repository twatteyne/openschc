import time
import sys
# insert at 1, 0 is the script path (or '' in REPL)
sys.path.insert(1, '../../src/')

from gen_utils import dprint, sanitize_value
from compr_core import *

from scapy.all import hexdump


class ScapyUpperLayer:
    def __init__(self):
        self.protocol = None

    # ----- AbstractUpperLayer interface (see: architecture.py)
    
    def _set_protocol(self, protocol):
        self.protocol = protocol

    def recv_packet(self, address, raw_packet):
        raise NotImplementedError("XXX:to be implemented")

    # ----- end AbstractUpperLayer interface

    def send_later(self, delay, udp_dst, packet):
        assert self.protocol is not None
        scheduler = self.protocol.get_system().get_scheduler()
        scheduler.add_event(delay, self._send_now, (udp_dst, packet))

    def _send_now(self, packet):
        #dst_address = address_to_string(udp_dst)
        self.protocol.schc_send(packet)

# --------------------------------------------------        

class ScapyLowerLayer:
    def __init__(self, position, socket=None, other_end=None):
        self.protocol = None
        self.position = position
        self.other_end = other_end
        self.sock = socket

    # ----- AbstractLowerLayer interface (see: architecture.py)
        
    def _set_protocol(self, protocol):
        self.protocol = protocol
        self._actual_init()

    def send_packet(self, packet, dest, transmit_callback=None):
        print("SENDING", packet, dest)            

        if self.position == T_POSITION_CORE:
            if dest != None and dest.find("udp") == 0:
                destination = (dest.split(":")[1], int(dest.split(":")[2]))
            else:
                print ("No destination found, not sent")
                return False
        else:
            destination = self.other_end

            print (destination)
            hexdump(packet)
            self.sock.sendto(packet, destination)

        print ("L2 send_packet", transmit_callback)
        if transmit_callback is not None:
            print ("do callback", transmit_callback)
            transmit_callback(1)
        else:
            print ("c'est None")

    def get_mtu_size(self):
        return 72 # XXX

    # ----- end AbstractLowerLayer interface

    def _actual_init(self):
        pass

    def event_packet_received(self):
        """Called but the SelectScheduler when an UDP packet is received"""
        packet, address = self.sd.recvfrom(MAX_PACKET_SIZE)
        sender_address = address_to_string(address)
        self.protocol.schc_recv(sender_address, packet)


class ScapyScheduler:
    def __init__(self):
        self.queue = []
        self.clock = 0
        self.next_event_id = 0
        self.current_event_id = None
        self.observer = None
        self.item=0
        self.fd_callback_table = {}
        self.last_show = 0 


    # ----- AbstractScheduler Interface (see: architecture.py)

    def get_clock(self):
        return time.time()
         
    def add_event(self, rel_time, callback, args):
        #print("Add event {}".format(sanitize_value(self.queue)))
        #print("callback set -> {}".format(callback.__name__))
        assert rel_time >= 0
        event_id = self.next_event_id
        self.next_event_id += 1
        clock = self.get_clock()
        abs_time = clock+rel_time
        self.queue.append((abs_time, event_id, callback, args))
        return event_id

    def cancel_event(self, event):
        print ("remove event", event)

        item_pos = 0
        item_found = False
        elm = None
        for q in self.queue:
            if q[1] == event:
                item_found = True
                break
            item_pos += 1

        if item_found:
            print ("item found", item_pos)
            elm = self.queue.pop(item_pos)
            print (self.queue)

        return elm

    # ----- Additional methods

    def _sleep(self, delay):
        """Implements a delayfunc for sched.scheduler
        This delayfunc sleeps for `delay` seconds at most (in real-time,
        but if any event appears in the fd_table (e.g. packet arrival),
        the associated callbacks are called and the wait is stop.
        """
        self.wait_one_callback_until(delay)


    def wait_one_callback_until(self, max_delay):
        """Wait at most `max_delay` second, for available input (e.g. packet).
        If so, all associated callbacks are run until there is no input.
        """
        fd_list = list(sorted(self.fd_callback_table.keys()))
        print (fd_list)
        while True:
            rlist, unused, unused = select.select(fd_list, [], [], max_delay)
            if len(rlist) == 0:
                break
            for fd in rlist:
                callback, args = self.fd_callback_table[fd]
                callback(*args)
            # note that sched impl. allows to return before sleeping `delay`

    def add_fd_callback(self, fd, callback, args):
        assert fd not in self.fd_callback_table
        self.fd_callback_table[fd] = (callback, args)

    def run(self, session=None, period=None):
        factor= 10
        if self.item % factor == 0:
            seq = ["|", "/", "-", "\\", "-"]
            print ("{:s}".format(seq[(self.item//factor)%len(seq)]),end="\b", flush=True)
        self.item +=1

        if period and time.time() - self.last_show > period: # display the event queue every minute
            print ("*"*40)
            print ("EVENT QUEUE")
            self.last_show = time.time()
            for q in self.queue:
                print ("{0:6.2f}: id.{1:04d}".format(q[0]-time.time(), q[1]), q[2])
            print ("*"*40)

            if session:
                print(session.session_manager.session_table)


        while len(self.queue) > 0:
            self.queue.sort()

            wake_up_time = self.queue[0][0]
            if time.time() < wake_up_time:
                return

            event_info = self.queue.pop(0)
            self.clock, event_id, callback, args = event_info
            self.current_event_id = event_id
            if self.observer is not None:
                self.observer("sched-pre-event", event_info)
            callback(*args)
            if self.observer is not None:
                self.observer("sched-post-event", event_info)
            print("Queue running event -> {}, callback -> {}".format(event_id, callback.__name__))

# --------------------------------------------------        

class ScapySystem:
    def __init__(self):
        self.scheduler = ScapyScheduler()

    def get_scheduler(self):
        return self.scheduler

    def log(self, name, message):
        print(name, message)

# --------------------------------------------------