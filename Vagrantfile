Vagrant.configure("2") do |config|
  config.vm.box = "generic/ubuntu2204"
  config.vm.hostname = "niep-py3"

  # Sync current repository into guest.
  config.vm.synced_folder ".", "/home/vagrant/NIEP"

  config.vm.provider :libvirt do |libvirt|
    libvirt.cpus = 4
    libvirt.memory = 4096
	libvirt.management_network_name = "vagrant-libvirt"
  	libvirt.management_network_address = "192.168.250.0/24"
  end

  config.vm.provision "shell", inline: <<-SHELL
    set -euo pipefail
    cd /home/vagrant/NIEP
    chmod +x INSTALLATION/installer.sh INSTALLATION/provision-vm.sh INSTALLATION/setup-py3-dev.sh
    sudo INSTALLATION/installer.sh --repo /home/vagrant/NIEP --user vagrant
  SHELL
end
