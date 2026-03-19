#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <ca|client> <name> [output-dir]" >&2
  exit 1
fi

mode="$1"
name="$2"
outdir="${3:-./mtls}"

mkdir -p "$outdir"

case "$mode" in
  ca)
    openssl genrsa -out "$outdir/${name}-ca.key" 4096
    openssl req -x509 -new -nodes \
      -key "$outdir/${name}-ca.key" \
      -sha256 \
      -days 3650 \
      -out "$outdir/${name}-ca.pem" \
      -subj "/CN=${name} Upload Client CA"
    echo "created CA:"
    echo "  key: $outdir/${name}-ca.key"
    echo "  cert: $outdir/${name}-ca.pem"
    ;;
  client)
    if [[ ! -f "$outdir/upload-client-ca.key" || ! -f "$outdir/upload-client-ca.pem" ]]; then
      echo "expected CA files:" >&2
      echo "  $outdir/upload-client-ca.key" >&2
      echo "  $outdir/upload-client-ca.pem" >&2
      echo "create them first with:" >&2
      echo "  $0 ca upload-client $outdir" >&2
      exit 1
    fi

    extfile="$outdir/${name}.client.ext"
    cat >"$extfile" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

    openssl genrsa -out "$outdir/${name}.key" 2048
    openssl req -new \
      -key "$outdir/${name}.key" \
      -out "$outdir/${name}.csr" \
      -subj "/CN=${name}"
    openssl x509 -req \
      -in "$outdir/${name}.csr" \
      -CA "$outdir/upload-client-ca.pem" \
      -CAkey "$outdir/upload-client-ca.key" \
      -CAcreateserial \
      -out "$outdir/${name}.crt" \
      -days 825 \
      -sha256 \
      -extfile "$extfile"
    rm -f "$extfile"
    echo "created client cert:"
    echo "  key: $outdir/${name}.key"
    echo "  csr: $outdir/${name}.csr"
    echo "  cert: $outdir/${name}.crt"
    ;;
  *)
    echo "unknown mode: $mode" >&2
    exit 1
    ;;
esac
