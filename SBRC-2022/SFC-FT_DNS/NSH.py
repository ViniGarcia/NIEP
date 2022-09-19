################################################## NSH AREA ###################################################

class NSH:

	base_version = None   #Bit [0;1]
	base_0bit = None	  #Bit 2
	base_ttl = None		  #Bit [4;9]
	base_length = None    #Bit [10;15]
	base_mdtype = None    #Bit [20;23]
	base_nextprot = None  #Bit [24;31]

	service_spi = None    #Bit [0;23]
	service_si = None     #Bit [24;31]

	context_data = None   #Byte [0;16] (fixed-length only)


	def fromHeader(self, header):

		if len(header) != 24:
			return -1

		self.base_version = header[0] & 3
		self.base_0bit = (header[0] & 4) >> 2
		self.base_ttl = ((header[0] & 240) >> 4) | ((header[1] & 3) << 4)
		self.base_length = (header[1] & 252) >> 2
		self.base_mdtype = (header[2] & 240) >> 4
		self.base_nextprot = header[3]

		self.service_spi = header[4] | header[5] << 8 | header[6] << 16
		self.service_si = header[7]

		self.context_data = header[8:]

	def toHeader(self):

		if self.base_version == None:
			return -1

		header = []
		header.append(self.base_version + (self.base_0bit << 2) + ((self.base_ttl & 15) << 4))
		header.append(((self.base_ttl & 48) >> 4) + (self.base_length << 2))
		header.append(self.base_mdtype << 4)
		header.append(self.base_nextprot)
		header.append(self.service_spi & 255)
		header.append((self.service_spi & 65280) >> 8)
		header.append((self.service_spi & 16711680) >> 16)
		header.append(self.service_si)
		header += self.context_data

		return bytearray(header)

	def newHeader(self, base_version, base_ttl, base_mdtype, base_nextprot, service_spi, service_si, context_data):

		if not isinstance(base_version, int):
			return -1
		if not isinstance(base_ttl, int):
			return -2
		if not isinstance(base_mdtype, int):
			return -3
		if not isinstance(base_nextprot, int):
			return -4
		if not isinstance(service_spi, int):
			return -5
		if not isinstance(service_si, int):
			return -6
		if not isinstance(context_data, bytearray):
			return -7

		if base_version < 0 or base_version > 3:
			return -8
		if base_ttl < 0 or base_ttl > 63:
			return -9
		if base_mdtype < 0 or base_mdtype > 15:
			return -10
		if base_nextprot < 0 or base_nextprot > 255:
			return -11
		if service_spi < 0 or service_spi > 16777215:
			return -12
		if service_si < 0 or service_si > 255:
			return -13
		if len(context_data) != 16:
			return -14

		self.base_version = base_version
		self.base_0bit = 0
		self.base_length = 24
		self.base_ttl = base_ttl
		self.base_mdtype = base_mdtype
		self.base_nextprot = base_nextprot
		self.service_spi = service_spi
		self.service_si = service_si
		self.context_data = context_data

		return self.toHeader()

###############################################################################################################