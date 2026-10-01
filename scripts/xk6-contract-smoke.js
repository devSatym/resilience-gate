import { Client } from 'k6/x/ethereum';

const RPC_URL = __ENV.RPC_URL || 'https://rpc.testnet.radiustech.xyz';
const SERVICE_WALLET = __ENV.SERVICE_WALLET_ADDRESS;
const WALLET_KEY = __ENV.WALLET_KEY_1;
const SBC_CONTRACT = (__ENV.SBC_CONTRACT_ADDRESS || '0x33ad9e4bd16b69b5bfded37d8b5d9ff9aba014fb').toLowerCase();
const SBC_AMOUNT = parseInt(__ENV.SBC_AMOUNT || '1000', 10);
const TX_GAS_LIMIT = parseInt(__ENV.TX_GAS_LIMIT || '100000', 10);

const ERC20_ABI = JSON.stringify([
  {
    type: 'function',
    name: 'transfer',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'to', type: 'address' },
      { name: 'value', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    type: 'function',
    name: 'balanceOf',
    stateMutability: 'view',
    inputs: [{ name: 'account', type: 'address' }],
    outputs: [{ name: '', type: 'uint256' }],
  },
]);

if (!SERVICE_WALLET) {
  throw new Error('SERVICE_WALLET_ADDRESS is required');
}

if (!WALLET_KEY) {
  throw new Error('WALLET_KEY_1 is required');
}

export const options = {
  vus: 1,
  iterations: 1,
};

const client = new Client({
  url: RPC_URL,
  privateKey: WALLET_KEY, // no 0x prefix
});

const token = client.newContract(SBC_CONTRACT, ERC20_ABI);

export default function () {
  let sender = 'unknown';
  try {
    const owned = client.accounts();
    if (owned && owned.length > 0) {
      sender = owned[0];
    }
  } catch (_) {
    // Some providers disable account discovery; not fatal for this smoke test.
  }

  console.log(`RPC: ${RPC_URL}`);
  console.log(`SBC contract: ${SBC_CONTRACT}`);
  console.log(`Sender: ${sender}`);
  console.log(`Recipient: ${SERVICE_WALLET}`);
  console.log(`Amount: ${SBC_AMOUNT}`);

  try {
    const txHash = token.txn(
      'transfer',
      { gas_limit: TX_GAS_LIMIT },
      SERVICE_WALLET,
      SBC_AMOUNT,
    );
    console.log(`transfer() succeeded: ${txHash}`);
  } catch (e) {
    console.error(`transfer() failed: ${e}`);
    throw e;
  }
}
