import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { Keypair, TransactionMessage, VersionedTransaction, TransactionInstruction, SystemProgram, ComputeBudgetProgram, PublicKey } from '@solana/web3.js';
import { CAP, fundingAmount, validateCreate } from '../launch/guard.mjs';
import { deliverOnce } from '../launch/transport.mjs';
const idl=JSON.parse(fs.readFileSync(new URL('../vendor/PumpIdl.json',import.meta.url)));
const payer=Keypair.generate().publicKey, mint=Keypair.generate().publicKey;
const expected={payer:payer.toBase58(),mint:mint.toBase58(),name:'Orbit Bloom',symbol:'ORB',uri:'https://ipfs.io/ipfs/test'};
function string(s){const b=Buffer.from(s);const n=Buffer.alloc(4);n.writeUInt32LE(b.length);return Buffer.concat([n,b]);}
function instruction(version='create'){
  const def=idl.instructions.find(i=>i.name===version);
  const keys=def.accounts.map(a=>({pubkey:a.name==='mint'?mint:a.name==='user'?payer:Keypair.generate().publicKey,isSigner:!!a.signer,isWritable:!!a.writable}));
  const data=Buffer.concat([Buffer.from(def.discriminator),string(expected.name),string(expected.symbol),string(expected.uri),payer.toBuffer(),...(version==='create_v2'?[Buffer.alloc(11)]:[])]);
  return new TransactionInstruction({programId:new PublicKey(idl.address),keys,data});
}
function tx(ixs){return new VersionedTransaction(new TransactionMessage({payerKey:payer,recentBlockhash:Keypair.generate().publicKey.toBase58(),instructions:ixs}).compileToV0Message());}
test('funding and its fee cannot exceed authorized cap',()=>{assert.equal(fundingAmount(5000)+5000,CAP);for(const n of [null,NaN,-1,0.1,CAP,Infinity])assert.throws(()=>fundingAmount(n));});
test('accept exact create and create_v2',()=>{for(const v of ['create','create_v2'])assert.equal(validateCreate(tx([instruction(v)]),expected),true);});
test('reject appended SOL drain instruction',()=>{assert.throws(()=>validateCreate(tx([instruction(),SystemProgram.transfer({fromPubkey:payer,toPubkey:Keypair.generate().publicKey,lamports:1})]),expected),/Unexpected program/);});
test('reject wrong creator and changed token metadata',()=>{const t=tx([instruction()]);assert.throws(()=>validateCreate(t,{...expected,name:'Impersonation'}),/Metadata/);assert.throws(()=>validateCreate(t,{...expected,payer:Keypair.generate().publicKey.toBase58()}),/signers/);});
test('reject double create and excessive priority price',()=>{assert.throws(()=>validateCreate(tx([instruction(),instruction()]),expected));assert.throws(()=>validateCreate(tx([ComputeBudgetProgram.setComputeUnitPrice({microLamports:100001}),instruction()]),expected),/compute/);});
test('reject buy disguised as Pump instruction',()=>{const i=instruction();i.data[0]^=255;assert.throws(()=>validateCreate(tx([i]),expected),/Only one/);});
test('reject unexpected launch options',()=>{const i=instruction('create_v2');i.data[i.data.length-11]=1;assert.throws(()=>validateCreate(tx([i]),expected),/launch mode/);});
test('actual unsigned PumpPortal zero-buy response with resolved lookup tables',()=>{const f=JSON.parse(fs.readFileSync(new URL('./ProviderFixture.json',import.meta.url)));const t=VersionedTransaction.deserialize(Buffer.from(f.raw,'base64'));assert.equal(validateCreate(t,f.expected,f.keys),true);assert.throws(()=>validateCreate(t,f.expected),/must be resolved/);assert.ok(t.signatures.every(s=>s.every(b=>b===0)));});
test('ambiguous network response never causes a second send, including restart',async()=>{
  let state={funding:{signature:'test',raw:'dGVzdA=='}};let durable;let sends=0;
  const rpc={getSignatureStatuses:async()=>({value:[null]}),sendRawTransaction:async()=>{assert.equal(durable.funding.attempted,true);sends++;throw Error('timeout');}};
  const save=()=>{durable=JSON.parse(JSON.stringify(state));};
  assert.equal(await deliverOnce(state,'funding',rpc,save,()=>false,async()=>{}),false);
  state=JSON.parse(JSON.stringify(durable));
  assert.equal(await deliverOnce(state,'funding',rpc,save,()=>false,async()=>{}),false);
  assert.equal(sends,1);assert.equal(state.status,'pending');
});
test('finalized success and failure are reconciled without resending',async()=>{
  for(const err of [null,{InstructionError:[0,'Custom']}]){
    const state={funding:{signature:'test',raw:'',attempted:true}};
    const rpc={getSignatureStatuses:async()=>({value:[{confirmationStatus:'finalized',err}]}),sendRawTransaction:async()=>assert.fail('must not send')};
    assert.equal(await deliverOnce(state,'funding',rpc,()=>{},()=>false,async()=>{}),!err);
    if(err)assert.equal(state.status,'failed');
  }
});
test('pause prevents a not-yet-broadcast transaction',async()=>{
  const state={funding:{signature:'test',raw:''}};
  const rpc={getSignatureStatuses:async()=>({value:[null]}),sendRawTransaction:async()=>assert.fail('paused')};
  assert.equal(await deliverOnce(state,'funding',rpc,()=>{},()=>true,async()=>{}),false);
  assert.equal(state.funding.attempted,undefined);
});
