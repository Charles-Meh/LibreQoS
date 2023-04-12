from pythonCheck import checkPythonVersion
checkPythonVersion()
import requests
import os
import csv
from integrationCommon import isIpv4Permitted, fixSubnet
try:
	from ispConfig import uispSite, uispStrategy, overwriteNetworkJSONalways
except:
	from ispConfig import uispSite, uispStrategy
	overwriteNetworkJSONalways = False

def uispRequest(target):
	# Sends an HTTP request to UISP and returns the
	# result in JSON. You only need to specify the
	# tail end of the URL, e.g. "sites"
	from ispConfig import UISPbaseURL, uispAuthToken
	url = UISPbaseURL + "/nms/api/v2.1/" + target
	headers = {'accept': 'application/json', 'x-auth-token': uispAuthToken}
	r = requests.get(url, headers=headers, timeout=10)
	return r.json()

def buildFlatGraph():
	# Builds a high-performance (but lacking in site or AP bandwidth control)
	# network.
	from integrationCommon import NetworkGraph, NetworkNode, NodeType
	from ispConfig import generatedPNUploadMbps, generatedPNDownloadMbps

	# Load network sites
	print("Loading Data from UISP")
	sites = uispRequest("sites")
	devices = uispRequest("devices?withInterfaces=true&authorized=true")

	# Build a basic network adding every client to the tree
	print("Building Flat Topology")
	net = NetworkGraph()

	for site in sites:
		type = site['identification']['type']
		if type == "endpoint":
			id = site['identification']['id']
			address = site['description']['address']
			customerName = ''
			name = site['identification']['name']
			type = site['identification']['type']
			download = generatedPNDownloadMbps
			upload = generatedPNUploadMbps
			if (site['qos']['downloadSpeed']) and (site['qos']['uploadSpeed']):
				download = int(round(site['qos']['downloadSpeed']/1000000))
				upload = int(round(site['qos']['uploadSpeed']/1000000))

			node = NetworkNode(id=id, displayName=name, type=NodeType.client, download=download, upload=upload, address=address, customerName=customerName)
			net.addRawNode(node)
			for device in devices:
				if device['identification']['site'] is not None and device['identification']['site']['id'] == id:
					# The device is at this site, so add it
					ipv4 = []
					ipv6 = []

					for interface in device["interfaces"]:
						for ip in interface["addresses"]:
							ip = ip["cidr"]
							if isIpv4Permitted(ip):
								ip = fixSubnet(ip)
								if ip not in ipv4:
									ipv4.append(ip)

					# TODO: Figure out Mikrotik IPv6?
					mac = device['identification']['mac']

					net.addRawNode(NetworkNode(id=device['identification']['id'], displayName=device['identification']
						['name'], parentId=id, type=NodeType.device, ipv4=ipv4, ipv6=ipv6, mac=mac))

	# Finish up
	net.prepareTree()
	net.plotNetworkGraph(False)
	if net.doesNetworkJsonExist():
		if overwriteNetworkJSONalways:
			net.createNetworkJson()
		else:
			print("network.json already exists and overwriteNetworkJSONalways set to False. Leaving in-place.")
	else:
		net.createNetworkJson()
	net.createShapedDevices()

def linkSiteTarget(link, direction):
	# Helper function to extract the site ID from a data link. Returns
	# None if not present.
	if link[direction]['site'] is not None:
		return link[direction]['site']['identification']['id']
	
	return None

def findSiteLinks(dataLinks, siteId):
	# Searches the Data Links for any links to/from the specified site.
	# Returns a list of site IDs that are linked to the specified site.
	links = []
	for dl in dataLinks:
		fromSiteId = linkSiteTarget(dl, "from")
		if fromSiteId is not None and fromSiteId == siteId:
			# We have a link originating in this site.
			target = linkSiteTarget(dl, "to")
			if target is not None:
				links.append(target)

		toSiteId = linkSiteTarget(dl, "to")
		if toSiteId is not None and toSiteId == siteId:
			# We have a link originating in this site.
			target = linkSiteTarget(dl, "from")
			if target is not None:
				links.append(target)
	return links

def buildSiteBandwidths():
	# Builds a dictionary of site bandwidths from the integrationUISPbandwidths.csv file.
	siteBandwidth = {}
	if os.path.isfile("integrationUISPbandwidths.csv"):
		with open('integrationUISPbandwidths.csv') as csv_file:
			csv_reader = csv.reader(csv_file, delimiter=',')
			next(csv_reader)
			for row in csv_reader:
				name, download, upload = row
				download = int(download)
				upload = int(upload)
				siteBandwidth[name] = {"download": download, "upload": upload}
	return siteBandwidth

def findApCapacities(devices, siteBandwidth):
	# Searches the UISP devices for APs and adds their capacities to the siteBandwidth dictionary.
	for device in devices:
		if device['identification']['role'] == "ap":
			name = device['identification']['name']
			if not name in siteBandwidth and device['overview']['downlinkCapacity'] and device['overview']['uplinkCapacity']:
				download = int(device['overview']
							   ['downlinkCapacity'] / 1000000)
				upload = int(device['overview']['uplinkCapacity'] / 1000000)
				siteBandwidth[device['identification']['name']] = {
					"download": download, "upload": upload}

def findAirfibers(devices, generatedPNDownloadMbps, generatedPNUploadMbps):
	foundAirFibersBySite = {}
	for device in devices:
		if device['identification']['site']['type'] == 'site':
			if device['identification']['role'] == "station":
				if device['identification']['type'] == "airFiber":
					if device['overview']['status'] == 'active':
						if device['overview']['downlinkCapacity'] is not None and device['overview']['uplinkCapacity'] is not None:
							download = int(device['overview']['downlinkCapacity']/ 1000000)
							upload = int(device['overview']['uplinkCapacity']/ 1000000)
						else:
							download = generatedPNDownloadMbps
							upload = generatedPNUploadMbps
						# Make sure to use half of reported bandwidth for AF60-LRs
						if device['identification']['model'] == "AF60-LR":
							download = int(download / 2)
							upload = int(download / 2)
						if device['identification']['site']['id'] in foundAirFibersBySite:
							if (download > foundAirFibersBySite[device['identification']['site']['id']]['download']) or (upload > foundAirFibersBySite[device['identification']['site']['id']]['upload']):
								foundAirFibersBySite[device['identification']['site']['id']]['download'] = download
								foundAirFibersBySite[device['identification']['site']['id']]['upload'] = upload
						else:
							foundAirFibersBySite[device['identification']['site']['id']] = {'download': download, 'upload': upload}
	return foundAirFibersBySite

def buildSiteList(sites, dataLinks):
	# Builds a list of sites, including their IDs, names, and connections.
	# Connections are determined by the dataLinks list.
	siteList = []
	for site in sites:
		newSite = {
			'id': site['identification']['id'], 
			'name': site['identification']['name'],
			'connections': findSiteLinks(dataLinks, site['identification']['id']),
			'cost': 10000,
			'parent': "",
			'type': type,
		}
		siteList.append(newSite)
	return siteList

def findInSiteList(siteList, name):
	# Searches the siteList for a site with the specified name.
	for site in siteList:
		if site['name'] == name:
			return site
	return None

def findInSiteListById(siteList, id):
	# Searches the siteList for a site with the specified name.
	for site in siteList:
		if site['id'] == id:
			return site
	return None

def debugSpaces(n):
	# Helper function to print n spaces.
	spaces = ""
	for i in range(int(n)):
		spaces = spaces + " "
	return spaces

def walkGraphOutwards(siteList, root, routeOverrides):
	def walkGraph(node, parent, cost, backPath):
		site = findInSiteListById(siteList, node)
		routeName = parent['name'] + "->" + site['name']
		if routeName in routeOverrides:
			# We have an overridden cost for this route, so use it instead
			#print("--> Using overridden cost for " + routeName + ". New cost: " + str(routeOverrides[routeName]) + ".")
			cost = routeOverrides[routeName]
		if cost < site['cost']:
			# It's cheaper to get here this way, so update the cost and parent.
			site['cost'] = cost
			site['parent'] = parent['id']
			#print(debugSpaces(cost/10) + parent['name'] + "->" + site['name'] + " -> New cost: " + str(cost))

		for connection in site['connections']:
			if not connection in backPath:
				#target = findInSiteListById(siteList, connection)
				#print(debugSpaces((cost+10)/10) + site['name'] + " -> " + target['name'] + " (" + str(target['cost']) + ")")
				newBackPath = backPath.copy()
				newBackPath.append(site['id'])
				walkGraph(connection, site, cost+10, newBackPath)

	for connection in root['connections']:
		# Force the parent since we're at the top
		site = findInSiteListById(siteList, connection)
		site['parent'] = root['id']
		walkGraph(connection, root, 10, [root['id']])

def loadRoutingOverrides():
	# Loads integrationUISProutes.csv and returns a set of "from", "to", "cost"
	overrides = {}
	if os.path.isfile("integrationUISProutes.csv"):
		with open("integrationUISProutes.csv", "r") as f:
			reader = csv.reader(f)
			for row in reader:
				if not row[0].startswith("#") and len(row) == 3:
					fromSite, toSite, cost = row
					overrides[fromSite.strip() + "->" + toSite.strip()] = int(cost)
	#print(overrides)
	return overrides

def buildFullGraph():
	# Attempts to build a full network graph, incorporating as much of the UISP
	# hierarchy as possible.
	from integrationCommon import NetworkGraph, NetworkNode, NodeType
	from ispConfig import generatedPNUploadMbps, generatedPNDownloadMbps

	# Load network sites
	print("Loading Data from UISP")
	sites = uispRequest("sites")
	devices = uispRequest("devices?withInterfaces=true&authorized=true")
	dataLinks = uispRequest("data-links?siteLinksOnly=true")

	# Build Site Capacities
	siteBandwidth = buildSiteBandwidths()
	findApCapacities(devices, siteBandwidth)
	foundAirFibersBySite = findAirfibers(devices, generatedPNDownloadMbps, generatedPNUploadMbps)
	
	# Create a list of just network sites
	siteList = buildSiteList(sites, dataLinks)
	rootSite = findInSiteList(siteList, uispSite)
	routeOverrides = loadRoutingOverrides()
	if rootSite is None:
		print("ERROR: Unable to find root site in UISP")
		return
	walkGraphOutwards(siteList, rootSite, routeOverrides)
	# Debug code: dump the list of site parents
	# for s in siteList:
	# 	if s['parent'] == "":
	# 		p = "None"
	# 	else:
	# 		p = findInSiteListById(siteList, s['parent'])['name']
	# 		print(s['name'] + " (" + str(s['cost']) + ") <-- " + p)
	
	# Find Nodes Connected By PtMP
	nodeOffPtMP = {}
	for site in sites:
		id = site['identification']['id']
		name = site['identification']['name']
		type = site['identification']['type']
		parent = findInSiteListById(siteList, id)['parent']
		if type == 'site':
			for link in dataLinks:
				if link['from']['site'] is not None and link['from']['site']['identification']['id'] == parent:
					if link['to']['site'] is not None and link['to']['site']['identification']['id'] == id:
						if link['from']['device'] is not None and link['to']['device'] is not None and link['to']['device']['overview'] is not None and link['to']['device']['overview']['downlinkCapacity'] is not None and link['from']['device']['overview']['wirelessMode'] == 'ap-ptmp':
							# Capacity of the PtMP client radio feeding the PoP will be used as the site bandwidth limit
							download = int(round(link['to']['device']['overview']['downlinkCapacity']/1000000))
							upload = int(round(link['to']['device']['overview']['uplinkCapacity']/1000000))
							nodeOffPtMP[id] = { 'parent': link['from']['device']['identification']['id'],
												'download': download,
												'upload': upload
												}
	print("Building Topology")
	net = NetworkGraph()
	# Add all sites and client sites
	for site in sites:
		id = site['identification']['id']
		name = site['identification']['name']
		type = site['identification']['type']
		download = generatedPNDownloadMbps
		upload = generatedPNUploadMbps
		address = ""
		customerName = ""
		parent = findInSiteListById(siteList, id)['parent']
		if parent == "":
			if site['identification']['parent'] is None:
				parent = ""
			else:
				parent = site['identification']['parent']['id']
		match type:
			case "site":
				nodeType = NodeType.site
				if id in nodeOffPtMP:
					parent = nodeOffPtMP[id]['parent']
				if name in siteBandwidth:
					# Use the CSV bandwidth values
					download = siteBandwidth[name]["download"]
					upload = siteBandwidth[name]["upload"]
				elif id in nodeOffPtMP:
					download = nodeOffPtMP[id]['download']
					upload = nodeOffPtMP[id]['upload']
				elif id in foundAirFibersBySite:
					download = foundAirFibersBySite[id]['download']
					upload = foundAirFibersBySite[id]['upload']
				else:
					# Add them just in case
					siteBandwidth[name] = {
						"download": download, "upload": upload}
			case default:
				nodeType = NodeType.client
				address = site['description']['address']
				try:
					customerName = site["ucrm"]["client"]["name"]
				except:
					customerName = ""
				if (site['qos']['downloadSpeed']) and (site['qos']['uploadSpeed']):
					download = int(round(site['qos']['downloadSpeed']/1000000))
					upload = int(round(site['qos']['uploadSpeed']/1000000))

		node = NetworkNode(id=id, displayName=name, type=nodeType,
						   parentId=parent, download=download, upload=upload, address=address, customerName=customerName)
		# If this is the uispSite node, it becomes the root. Otherwise, add it to the
		# node soup.
		if name == uispSite:
			net.replaceRootNode(node)
		else:
			net.addRawNode(node)

		for device in devices:
			if device['identification']['site'] is not None and device['identification']['site']['id'] == id:
				# The device is at this site, so add it
				ipv4 = []
				ipv6 = []

				for interface in device["interfaces"]:
					for ip in interface["addresses"]:
						ip = ip["cidr"]
						if isIpv4Permitted(ip):
							ip = fixSubnet(ip)
							if ip not in ipv4:
								ipv4.append(ip)

				# TODO: Figure out Mikrotik IPv6?
				mac = device['identification']['mac']

				net.addRawNode(NetworkNode(id=device['identification']['id'], displayName=device['identification']
							   ['name'], parentId=id, type=NodeType.device, ipv4=ipv4, ipv6=ipv6, mac=mac))

	# Now iterate access points, and look for connections to sites
	for node in net.nodes:
		if node.type == NodeType.device:
			for dl in dataLinks:
				if dl['from']['device'] is not None and dl['from']['device']['identification']['id'] == node.id:
					if dl['to']['site'] is not None and dl['from']['site']['identification']['id'] != dl['to']['site']['identification']['id']:
						target = net.findNodeIndexById(
							dl['to']['site']['identification']['id'])
						if target > -1:
							# We found the site
							if net.nodes[target].type == NodeType.client or net.nodes[target].type == NodeType.clientWithChildren:
								net.nodes[target].parentId = node.id
								node.type = NodeType.ap
								if node.displayName in siteBandwidth:
									# Use the bandwidth numbers from the CSV file
									node.uploadMbps = siteBandwidth[node.displayName]["upload"]
									node.downloadMbps = siteBandwidth[node.displayName]["download"]
								else:
									# Add some defaults in case they want to change them
									siteBandwidth[node.displayName] = {
										"download": generatedPNDownloadMbps, "upload": generatedPNUploadMbps}
	
	net.prepareTree()
	net.plotNetworkGraph(False)
	if net.doesNetworkJsonExist():
		if overwriteNetworkJSONalways:
			net.createNetworkJson()
		else:
			print("network.json already exists and overwriteNetworkJSONalways set to False. Leaving in-place.")
	else:
		net.createNetworkJson()
	net.createShapedDevices()

	# Save integrationUISPbandwidths.csv
	# (the newLine fixes generating extra blank lines)
	# Saves as .template as to not overwrite
	with open('integrationUISPbandwidths.template.csv', 'w', newline='') as csvfile:
		wr = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
		wr.writerow(['ParentNode', 'Download Mbps', 'Upload Mbps'])
		for device in siteBandwidth:
			entry = (
				device, siteBandwidth[device]["download"], siteBandwidth[device]["upload"])
			wr.writerow(entry)


def importFromUISP():
	match uispStrategy:
		case "full": buildFullGraph()
		case default: buildFlatGraph()


if __name__ == '__main__':
	importFromUISP()
