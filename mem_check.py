#! /usr/bin/python

import subprocess, shlex, logging, sys, getopt, time
from subprocess import call
import socket
import os, os.path, random

def run_cmd(cmd, cleanup=None):
	#args = shlex.split(cmd)
	try:
		output = subprocess.check_output(cmd, shell=True)
	except subprocess.CalledProcessError as e:
		print e.output
		if cleanup is not None:
			cleanup()
		sys.exit("cmd: " + cmd)
	return output

def query_free_mem(unit="MB"):
	cmd = "vmstat -s"
	vmstat_output = run_cmd(cmd)
	lines = vmstat_output.splitlines()
	mem_used = lines[1].lstrip().split()[0]
	mem = int(mem_used)
	if unit is "MB":
		return mem / 1024
	else:
		return mem

class check_mem_usage():
	def __init__(self, args=[]):
		mlnx_dev = "mlx5_dev"
		num_vf = 0
		server = False
		num_rules = 0
		try:
			opts, args = \
				getopt.getopt(args,"hi:n:s:r:",
					["interface=", "num_vf=", "server=", "num_rules="])
		except getopt.GetoptError:
			print 'mem_usage.py -i <interface> -n <num_vf> -s <0|1> -r <num_rules>'
			sys.exit(1)
		for opt, arg in opts:
			if opt == '-h':
				print ('mem_usage.py -i <interface> -n <num_vf> -s <0|1> -r <num_rules>')
				sys.exit()
			elif opt in ("-i", "--interface"):
				mlnx_dev = arg
			elif opt in ("-n", "--num_vf"):
				num_vf = int(arg)
			elif opt in ("-s", "--server"):
				server = bool(int(arg))
			elif opt in ("-r", "--num_rules"):
				num_rules= int(arg)

		logging.basicConfig()
		logger = logging.getLogger("mem_check")
		logger.setLevel(logging.DEBUG)

		if (num_rules > 0):
			rules_test = check_rule_mem(logger, mlnx_dev, num_rules)
			rules_test.run()
		else:
			rep_test = check_rep_mem(logger, mlnx_dev,server, num_vf)
			rep_test.run()


class check_rep_mem():
	def __init__(self, log, mlx5_dev, server=True, num_vf=1):
		self.logger= log
		self.mlnx_dev = mlx5_dev
		self.server = server
		self.num_vf = num_vf
		self.host = 'sw-mtx-003-022'
		self.port = 5000
		self.dmesg_file = "/tmp/page_usage"
		self.give_page_file = "/tmp/give_page"
		self.reclaim_page_file = "/tmp/reclaim_page"

		if (server):
			self.server_init()
		else:
			self.client_init()

	def find(self, substr, infile, outfile):
		with open(infile) as a, open(outfile, 'w') as b:
			for line in a:
				if substr in line:
					b.write(line)

	def find_count(self, substr, infile):
		count = 0
		with open(infile) as file:
			for line in file:
				words = line.split()
				count += int(words[words.index(substr) + 1].replace(",", ""))
		return count

	def clean_up(self):
		if (self.server):
			self.server_conn.close()
			self.stop_record_dmesg()
		else:
			self.client_socket.close()

	def check_rep_cmd(self, cmd):
		return run_cmd(cmd, self.clean_up)

	def client_setup_vf(self):
		cmd_current_vf = ("cat /sys/class/infiniband/" + self.mlnx_dev +
				"/device/mlx5_num_vfs")
		cmd_reset_vf = ("echo 0 > /sys/class/infiniband/" +
				self.mlnx_dev +
				"/device/mlx5_num_vfs")
		cmd_set_vf = ("echo "+ str(self.num_vf) +
				" > /sys/class/infiniband/" + self.mlnx_dev +
				"/device/mlx5_num_vfs")
		message = 'done'

		count = self.check_rep_cmd(cmd_current_vf)
		self.logger.debug("%s has %d VF enabled", self.mlnx_dev, int(count))
		if (int(count) > 0):
			self.logger.debug("Reseting %s num of VF to 0", self.mlnx_dev)
			self.check_rep_cmd(cmd_reset_vf)
			time.sleep(40)
		self.client_socket.send(message.encode())

		self.logger.debug("Setting %s num of VF to %d", self.mlnx_dev, self.num_vf)
		self.check_rep_cmd(cmd_set_vf)
		time.sleep(5)
		self.client_socket.send(message.encode())

	def start_record_dmesg(self):
		self.check_rep_cmd("echo 'func give_pages +p' > \
			/sys/kernel/debug/dynamic_debug/control")
		self.check_rep_cmd("echo 'func reclaim_pages +p' > \
				/sys/kernel/debug/dynamic_debug/control")
		self.check_rep_cmd("dmesg -C")
		cmd = ("dmesg -w > " + self.dmesg_file + " &")
		self.logger.debug("Saving dmesg to %s", self.dmesg_file)
		self.check_rep_cmd(cmd)

	def stop_record_dmesg(self):
		self.check_rep_cmd("killall dmesg")
		self.check_rep_cmd("echo -n '-p' > \
			/sys/kernel/debug/dynamic_debug/control")

	def server_init(self):
		server_socket = socket.socket()
		server_socket.bind((self.host, self.port))
		self.logger.info("Waiting for connection...")
		server_socket.listen(2)
		self.server_conn, address = server_socket.accept()
		self.logger.info("Connection from: " + str(address))

	def server_wait_for_vf(self):
		self.logger.info("Waiting for host VF")
		while True:
			data = self.server_conn.recv(1024).decode()
			if data.lower().strip() == 'done':
			    break

	def server_bringup_rep(self):
		self.check_rep_cmd("ifconfig rep0-1 up")
		time.sleep(3)
		self.logger.info("Bringup rep0-1")

	def client_init(self):
		self.client_socket = socket.socket()
		self.client_socket.connect((self.host, self.port))
		self.logger.info("Connected to: " + self.host + ":" + str(self.port))

	def check_rep(self):
		if (self.server):
			# Wait for host VF to reset
			self.server_wait_for_vf()
			self.start_record_dmesg()
			mem_before = query_free_mem()
			# Wait for host VF to setup
			self.server_wait_for_vf()
			#self.server_bringup_rep()
			mem_after = query_free_mem()
			self.stop_record_dmesg()
			self.server_conn.close()

			self.find("give_pages", self.dmesg_file, self.give_page_file)
			give_page = self.find_count("npages", self.give_page_file)
			self.find("reclaim_pages", self.dmesg_file, self.reclaim_page_file)
			reclaim_page = self.find_count("npages", self.reclaim_page_file)
			page_used = give_page - reclaim_page

			fw_mem_used = page_used * 4 / 1024
			mem_used = abs(mem_after - mem_before)

			self.logger.info("-----------------------------------------")
			self.logger.info("\tMemory Usage Total:\t%d MB", mem_used)
			self.logger.debug("\t  Before:\t%d MB", mem_before)
			self.logger.debug("\t  After:\t%d MB", mem_after)
			self.logger.info("\tFirmware Page:\t\t%d", page_used)
			self.logger.info("\tFirmware Memory:\t%d MB", fw_mem_used)
			self.logger.info("\tDriver Memory:\t\t%d MB", mem_used - fw_mem_used)
			self.logger.info("-----------------------------------------")
		else:
			self.client_setup_vf()
			self.client_socket.close()
			self.logger.info("Set up %d VFs done.", self.num_vf)

	def run(self):
		self.check_rep()

class check_rule_mem():
	def __init__(self, log, rep, num_rules=1, offload="on"):
		self.rules_script = "./tc-batch-l2-random-rule.sh"
		self.rep = rep
		self.num_rules = num_rules
		self.logger = log
		self.tmp_tc_dir = "/tmp/tc_batch"
		self.offload = offload
		log.debug("rep = %s, num_rules = %d, offload = %s",
				rep, num_rules, offload)
		if not os.path.exists(self.rules_script):
			self.logger.error("%d doesn't exist", rules_script)
			sys.exit(2)

	def rand_mac(self, bit_mask=0xff):
    		return "%02x:%02x:%02x:%02x:%02x:%02x" % (
			random.randint(0, 100),
			random.randint(0, 100),
			random.randint(0, 100),
			random.randint(0, 100),
			random.randint(0, 100),
			random.randint(0, 100) & bit_mask)

	def tc_cmd(self, skip, src_mac, dst_mac):
		return (("filter add dev %s prio 1 protocol ip parent ffff: flower %s src_mac %s dst_mac %s action drop\n") % (
			 self.rep, skip, src_mac, dst_mac))


	def setup_rep(self):
		cmd_list = []
		cmd_list.append("ifconfig " + self.rep + " up")
		cmd_list.append("tc qdisc del dev " + self.rep + " ingress > /dev/null")
		cmd_list.append("rm -rf " + self.tmp_tc_dir)
		cmd_list.append("mkdir " + self.tmp_tc_dir)
		cmd_list.append("ethtool -K " + self.rep + " hw-tc-offload " + self.offload)
		cmd_list.append("tc qdisc add dev " + self.rep + " ingress")
		self.logger.debug("Reset tc and offload")
		for cmd in cmd_list:
			run_cmd(cmd)
		time.sleep(1)

		file_index = 0
		file_path = (self.tmp_tc_dir + "/batch." + str(file_index))
		file = open(file_path, "w")
		if self.offload is "on":
			skip = "skip_sw"
		else:
			skip = "skip_hw"

		for num in range(0, self.num_rules):
			new_index = int(num / 50000)
			if (new_index != file_index):
				file_index = new_index
				file_path = (self.tmp_tc_dir + "/batch." + str(file_index))
				file.close()
				file = open(file_path, "a")
			src_mac = self.rand_mac(0xfe)
			dst_mac = self.rand_mac()
			tc_cmd = self.tc_cmd(skip, src_mac, dst_mac)
			file.write(tc_cmd)

		file.close()

	def setup_rules(self):
		for filename in os.listdir(self.tmp_tc_dir):
			cmd_insert_rules = ("tc -b " + self.tmp_tc_dir + "/" + filename)
			self.logger.debug(cmd_insert_rules)
			run_cmd(cmd_insert_rules)
		time.sleep(3)

	def check_rules(self):
		self.logger.info("Check mem usage of ovs rules")
		self.setup_rep()
		mem_before = query_free_mem()
		self.setup_rules()
		mem_after = query_free_mem()
		mem_used = abs(mem_after - mem_before)

		self.logger.info("-----------------------------------------")
		self.logger.info("\tMemory Usage Total:\t\t%d MB", mem_used)
		self.logger.debug("\t  Before:\t\t%d MB", mem_before)
		self.logger.debug("\t  After:\t\t%d MB", mem_after)
		self.logger.info("-----------------------------------------")

	def run(self):
		self.check_rules()

if __name__ == "__main__":
	test = check_mem_usage(sys.argv[1:])
	exit()
