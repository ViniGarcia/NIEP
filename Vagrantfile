Vagrant.configure("2") do |config|
  config.vm.box = "generic/ubuntu2204"
  # Pin the locally installed reference box.  Set NIEP_BOX_VERSION only when
  # deliberately testing a newer disposable VM; update ENVIRONMENT.md with the
  # verified version before changing this default.
  config.vm.box_version = ENV.fetch("NIEP_BOX_VERSION", "4.3.12")
  config.vm.hostname = "niep-py3"

  # Sync current repository into guest.
  config.vm.synced_folder ".", "/home/vagrant/NIEP",
    type: "rsync",
    # Keep guest reports between test stages and do not import host build output.
    rsync__exclude: [".venv/", ".git/", ".vagrant/", "build/", "dist/",
                    ".pytest_cache/", ".coverage*"]

  config.vm.provider :libvirt do |libvirt|
    libvirt.cpus = 4
    libvirt.memory = 4096
	libvirt.management_network_name = "vagrant-libvirt"
  	libvirt.management_network_address = "192.168.250.0/24"
  end

  config.vm.provision "shell", inline: <<-SHELL
    set -euo pipefail
    cd /home/vagrant/NIEP
    chmod +x INSTALLATION/installer.sh INSTALLATION/provision-vm.sh INSTALLATION/setup-py3-dev.sh tools/niep_doctor.py
    sudo INSTALLATION/installer.sh --repo /home/vagrant/NIEP --user vagrant
  SHELL
end
