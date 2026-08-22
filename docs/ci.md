# CI e integração

O gate rápido para pull requests roda sem root, Docker, libvirt, Mininet ou
checkout de Git LFS. A matriz cobre Python 3.10, 3.11 e 3.12 e cada variante
executa `make test`; esse é o único comando que define o resultado dos testes
host. O alvo publica JUnit e cobertura em `build/test-results/`. Cobertura é
informativa neste primeiro ciclo e não é um limite de merge.

Lint e formatação são executados apenas sobre o código mantido pelo NIEP. A
árvore vendorizada `OFCONTROLLERS/pox/` é explicitamente excluída, assim como
artefatos de build e ambientes virtuais. `make ci-check` também verifica links
locais, âncoras e caminhos de exemplos documentados sem depender da rede.

## Gates e isolamento

O job `privileged-integration` é executado somente por `workflow_dispatch` ou
por agendamento, em um runner dedicado com o label `niep-disposable`. O runner
deve ser uma máquina descartável, sem credenciais persistentes; o workflow
destrói a VM Vagrant no início e no fim, coleta estado residual mesmo após uma
falha e publica os diagnósticos. Pull requests não conseguem selecionar esse
runner. O job `heavy-throughput` é separado e informativo: cobre o cenário
iperf/Click, que tem limites de bitrate e perda no próprio teste e pode variar
com a carga do host.

Até haver evidência suficiente, somente os jobs host da matriz são candidatos
a checks obrigatórios de merge. O histórico necessário para promover a
integração privilegiada é mantido em
[`docs/ci/privileged-history.json`](ci/privileged-history.json). Cada entrada
deve conter strings não vazias para ID de execução, revisão e cenário, além de
um status entre `success`, `failure`, `failed`, `cancelled` e `skipped`, após
revisão dos artefatos. IDs são únicos; uma entrada inválida faz o verificador
falhar em vez de ser ignorada. O verificador local é:

```bash
python tools/ci/check_privileged_history.py \
  --history docs/ci/privileged-history.json
```

O mesmo schema é validado por `make ci-history` e, portanto, também faz parte
do check local do pipeline.

Para testar a promoção sem alterar o gate atual, acrescente `--enforce`.
Quando existirem pelo menos dez IDs distintos e bem-sucedidos, a política pode
ser revisada e o job tornado obrigatório por branch protection. O arquivo
começa vazio de propósito: nenhuma execução privilegiada é alegada neste
checkout.

## Diagnósticos e recuperação

Falhas do runner guardam saída do `make`, `vagrant status`, interfaces e rotas
de rede, redes/domínios libvirt, containers Docker e estado do guest. O cleanup
é sempre executado, mas os artefatos são preservados antes de destruir a VM.
Em um runner recuperável, `make vm-clean` pode ser usado manualmente; em um
runner dedicado, destruir e reprovisionar a VM é a recuperação preferida.
