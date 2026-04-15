#!/usr/bin/env bash
# Quick run script for fraud_detect
set -e

JAC_NUM_ACCOUNTS=${JAC_NUM_ACCOUNTS:-200}
JAC_TXS_PER_ACCOUNT=${JAC_TXS_PER_ACCOUNT:-8}
JAC_VELOCITY_THRESHOLD=${JAC_VELOCITY_THRESHOLD:-5}
JAC_AMOUNT_THRESHOLD=${JAC_AMOUNT_THRESHOLD:-5000.0}
JAC_SEED=${JAC_SEED:-42}

export JAC_NUM_ACCOUNTS JAC_TXS_PER_ACCOUNT JAC_VELOCITY_THRESHOLD JAC_AMOUNT_THRESHOLD JAC_SEED

echo "=== fraud_detect ==="
echo "  accounts:           $JAC_NUM_ACCOUNTS"
echo "  txs/account (max):  $((JAC_TXS_PER_ACCOUNT * 2))"
echo "  velocity threshold: $JAC_VELOCITY_THRESHOLD"
echo "  amount threshold:   $JAC_AMOUNT_THRESHOLD"
echo ""

jac run main.jac
