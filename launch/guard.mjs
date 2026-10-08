import { readFileSync } from 'node:fs';
import { PublicKey, ComputeBudgetProgram } from '@solana/web3.js';
export const CAP = 25_000_000;
export const MAX_ATTEMPTS = 5;
const idl = JSON.parse(readFileSync(new URL('../vendor/PumpIdl.json', import.meta.url)));

export function fundingAmount(fee) {
  if (!Number.isSafeInteger(fee) || fee < 0 || fee >= CAP) throw new Error('Invalid funding fee');
  return CAP - fee;
}

export async function resolveKeys(tx, rpc) {
  const lookups = tx.message.addressTableLookups || [];
  if(lookups.length > 4)throw new Error('Unexpected number of address tables');
  const tables=[];
  for(const lookup of lookups){
    const table=(await rpc.getAddressLookupTable(lookup.accountKey,{commitment:'finalized'})).value;
    if(!table)throw new Error('Address table not found');
    tables.push(table);
  }
  const keys=tx.message.getAccountKeys({addressLookupTableAccounts:tables});
  return Array.from({length:keys.length},(_,i)=>keys.get(i).toBase58());
}

export function validateCreate(tx, {payer, mint, name, symbol, uri}, resolvedKeys) {
  const m = tx.message;
  if (m.addressTableLookups?.length && !resolvedKeys) throw new Error('Address lookup tables must be resolved from finalized RPC');
  const keys = resolvedKeys || m.staticAccountKeys.map(k => k.toBase58());
  if (keys[0] !== payer || m.header.numRequiredSignatures !== 2 || !keys.slice(0,2).includes(mint)) throw new Error('Unexpected transaction signers');
  let creates = 0;
  for (const ix of m.compiledInstructions) {
    const program = keys[ix.programIdIndex];
    const bytes = Buffer.from(ix.data);
    if (program === ComputeBudgetProgram.programId.toBase58()) {
      if (!((bytes[0] === 2 && bytes.length === 5 && bytes.readUInt32LE(1) <= 1_400_000) ||
            (bytes[0] === 3 && bytes.length === 9 && bytes.readBigUInt64LE(1) <= 100_000n))) throw new Error('Unexpected compute budget');
      continue;
    }
    if (program !== idl.address) throw new Error('Unexpected program in creation transaction');
    const def = idl.instructions.find(i => ['create','create_v2'].includes(i.name) && Buffer.from(i.discriminator).equals(bytes.subarray(0,8)));
    if (!def || ++creates > 1) throw new Error('Only one create instruction is permitted; buys and sells are disabled');
    for (const [i,a] of def.accounts.entries()) {
      if (a.name === 'mint' && keys[ix.accountKeyIndexes[i]] !== mint) throw new Error('Mint mismatch');
      if (a.name === 'user' && keys[ix.accountKeyIndexes[i]] !== payer) throw new Error('Creator signer mismatch');
    }
    let offset = 8;
    function read(type) {
      if (type === 'string') {
        const size = bytes.readUInt32LE(offset); offset += 4;
        if (size > 2048 || offset + size > bytes.length) throw new Error('Invalid string');
        const value = bytes.subarray(offset, offset + size).toString('utf8'); offset += size; return value;
      }
      if (type === 'pubkey') {const v=new PublicKey(bytes.subarray(offset,offset+32)).toBase58();offset+=32;return v;}
      if (type === 'bool') {if(offset>=bytes.length || bytes[offset]>1)throw new Error('Invalid boolean');return Boolean(bytes[offset++]);}
      if (type === 'u64') {const v=bytes.readBigUInt64LE(offset);offset+=8;return v;}
      const name=type?.defined?.name;
      if (name==='OptionBool') return read('bool');
      if (name==='OptionU64') return read('u64');
      throw new Error('Unsupported instruction schema');
    }
    const values = {};
    for (const arg of def.args) {
      // Pump's backward-compatible OptionBool/OptionU64 wrappers permit omitted
      // trailing fields. Observed zero-buy provider form ends after mayhem=false.
      const optional=arg.type?.defined?.name;
      values[arg.name] = offset===bytes.length && ['OptionBool','OptionU64'].includes(optional)
        ? (optional==='OptionBool'?false:0n) : read(arg.type);
    }
    if(offset!==bytes.length)throw new Error('Unrecognized instruction data');
    if(values.name!==name || values.symbol!==symbol || values.uri!==uri || values.creator!==payer)throw new Error('Metadata or creator mismatch');
    if(values.is_mayhem_mode || values.is_cashback_enabled || values.is_holder_reward || (values.creator_fee_bps && values.creator_fee_bps!==0n))throw new Error('Unexpected launch mode');
  }
  if(creates!==1)throw new Error('Missing Pump creation instruction');
  return true;
}
