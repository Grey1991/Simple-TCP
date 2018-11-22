from sys import *
# from packet import *
import socket
import time
import pickle
import argparse


mytime = None
if platform == 'win32':
    mytime = time.clock
else:
    mytime = time.time
assert(mytime is not None)

class Packet:
    def __init__(self, seq, ack, syn=0, fin=0, data=''):
        self.seq_num=seq
        self.ack_num=ack
        self.syn=syn
        self.fin=fin
        self.data=data

def write_in_logfile(send_or_receive, transmit_time, type, packet, filename):
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num))
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num), file=filename)

class STP_receiver(object):
    def __init__(self, receiver_port, filename):
        self.receiver_port = receiver_port
        self.filename = filename

        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.my_socket.bind(('', self.receiver_port))
        self.receiver_log = open('Receiver_log.txt', 'w')
        self.start_time = mytime()
        self.rcv_buff = 1024
        self.receiver_isn = 154
        self.rcv_base = 0
        self.last_rcv_seq = 0
        self.sender_addr = ''
        self.rcv_length_dic = {}
        self.rcv_segments = []
        self.duplicate_seg_num = 0


    def three_way_handshake(self):
        while True:
            data, addr = self.my_socket.recvfrom(self.rcv_buff)
            recevied_massage = pickle.loads(data)
            if recevied_massage.syn == 1:
                self.start_time = mytime()
                write_in_logfile('rcv', mytime()-self.start_time, 'S', recevied_massage, self.receiver_log)
                syn_packet1 = Packet(self.receiver_isn, recevied_massage.seq_num + 1, syn=1)
                self.my_socket.sendto(pickle.dumps(syn_packet1), addr)
                write_in_logfile('snd', mytime()-self.start_time, 'SA', syn_packet1,self.receiver_log)
            if recevied_massage.syn == 0:
                write_in_logfile('rcv', mytime()-self.start_time,'A', recevied_massage, self.receiver_log)
                self.rcv_base = recevied_massage.seq_num
                break
        print('Connection established')
        self.transmission()

    def move_window(self, received_message):
        point = self.rcv_base + len(received_message.data)
        rcv_seq_list = [i[0] for i in self.rcv_segments]
        while point in rcv_seq_list:
            point += self.rcv_length_dic[point]
        self.rcv_base = point

    def send_ack(self, received_message, addr):
        send_message = Packet(received_message.ack_num, self.rcv_base)
        self.my_socket.sendto(pickle.dumps(send_message), addr)
        write_in_logfile('snd', mytime() - self.start_time, 'A', send_message, self.receiver_log)

    def transmission(self):
        while True:
            data, addr = self.my_socket.recvfrom(self.rcv_buff)
            received_message = pickle.loads(data)
            if received_message.fin != 1:
                if (received_message.seq_num, received_message.data) not in self.rcv_segments:
                    self.rcv_segments.append((received_message.seq_num,received_message.data))
                    self.rcv_length_dic[received_message.seq_num] = len(received_message.data)
                    write_in_logfile('rcv',mytime()-self.start_time,'D',received_message,self.receiver_log)
                    if received_message.seq_num == self.rcv_base:
                        self.move_window(received_message)
                        self.send_ack(received_message, addr)
                    else:
                        self.send_ack(received_message, addr)
                else:
                    self.duplicate_seg_num += 1
            else:
                self.last_rcv_seq = received_message.seq_num
                self.sender_addr = addr
                print('transmission finished')
                write_in_logfile('rcv', mytime()-self.start_time, 'F',received_message,self.receiver_log)
                break
        self.shutdown()

    def shutdown(self):
        fin_packet = Packet(self.receiver_isn+1, self.last_rcv_seq+1,fin=1)
        self.my_socket.sendto(pickle.dumps(fin_packet), self.sender_addr)
        write_in_logfile('snd',mytime()-self.start_time,'A',fin_packet,self.receiver_log)
        while True:
            data, addr = self.my_socket.recvfrom(self.rcv_buff)
            received_message = pickle.loads(data)
            write_in_logfile('rcv',mytime()-self.start_time,'A',received_message,self.receiver_log)
            break
        self.my_socket.close()
        self.receiver_log.close()
        print('receiver shutdown')
        self.store_file()

    def store_file(self):
        self.rcv_segments = sorted(self.rcv_segments)
        for i in self.rcv_segments:
            if type(i) != tuple:
                print(i)
        # self.rcv_segments = sorted(self.rcv_segments, key=lambda x: x[0])
        content = ''
        for i in self.rcv_segments:
            content += i[1]
        copy_file = open(self.filename,'w')
        copy_file.write(content)
        copy_file.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("port")
    parser.add_argument("filename")
    args = parser.parse_args()

    port = int(args.port)
    filename = args.filename

    # port = 3000
    # filename = 'file2.txt'

    stp_receiver = STP_receiver(port, filename)
    stp_receiver.three_way_handshake()
    log_content = []
    data_num = 0
    seg_num = 0
    with open('Receiver_log.txt') as file:
        for line in file:
            log_content.append(line.split())
    for i in log_content:
        if i[0] == 'rcv' and i[2] == 'D':
            data_num += int(i[4])
            seg_num += 1
    log = open('Receiver_log.txt', 'a')
    log.write('\n'
              'Amount of (original) Data Received: '+str(data_num)+'\n'
              'Number of (original) Data Segments Received: '+str(seg_num)+'\n'
              'Number of duplicate segments received: '+str(stp_receiver.duplicate_seg_num)+'\n')
    log.close()
    print('\n'
          'Amount of (original) Data Received: ' + str(data_num) + '\n'
          'Number of (original) Data Segments Received: ' + str(seg_num) + '\n'
          'Number of duplicate segments received: ' + str(stp_receiver.duplicate_seg_num) + '\n')

    # time_test = open('Time_test_2.txt', 'a')
    # time_test.write('{:<9}\n'.format(log_content[-1][1]))

