// Compatibility probe: asks for UNSIGNED bytes. Does not sign or broadcast.
import { Keypair, VersionedTransaction, Connection } from '@solana/web3.js';
import fs from 'node:fs';
import { validateCreate, resolveKeys } from './guard.mjs';
const payer=Keypair.generate().publicKey.toBase58(),mint=Keypair.generate().publicKey.toBase58();
const name='Gem Compatibility',symbol='GEMTEST',uri='https://example.com/gem-compatibility.json';
const res=await fetch('https://pumpportal.fun/api/trade-local',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({publicKey:payer,action:'create',tokenMetadata:{name,symbol,uri},mint,denominatedInSol:'true',amount:0,slippage:1,priorityFee:0.00001,pool:'pump',isMayhemMode:false}),signal:AbortSignal.timeout(20000)});
if(!res.ok){console.log(JSON.stringify({provider_status:res.status,compatible:false,signed:false,broadcast:false}));process.exitCode=1;}
else{const raw=new Uint8Array(await res.arrayBuffer());const tx=VersionedTransaction.deserialize(raw);const rpc=new Connection(process.env.SOLANA_RPC_URL||'https://api.mainnet-beta.solana.com',{commitment:'finalized',disableRetryOnRateLimit:true});const keys=await resolveKeys(tx,rpc);fs.writeFileSync(new URL('../tests/ProviderFixture.json',import.meta.url),JSON.stringify({raw:Buffer.from(raw).toString('base64'),keys,expected:{payer,mint,name,symbol,uri}},null,2));validateCreate(tx,{payer,mint,name,symbol,uri},keys);console.log(JSON.stringify({compatible:true,zero_buy:true,instructions:tx.message.compiledInstructions.length,signed:false,broadcast:false}));}
