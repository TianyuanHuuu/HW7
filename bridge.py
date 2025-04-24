def scan_blocks(chain, contract_info="contract_info.json"):
    from web3 import Web3
    from eth_account import Account

    # Validate chain argument
    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return

    # Connect to both chains
    w3_source = connect_to('source')
    w3_dest = connect_to('destination')

    # Load contract info
    info = get_contract_info(chain, contract_info)
    other_chain = 'destination' if chain == 'source' else 'source'
    other_info = get_contract_info(other_chain, contract_info)

    # Contract instances
    w3 = w3_source if chain == 'source' else w3_dest
    contract = w3.eth.contract(address=Web3.to_checksum_address(info['address']), abi=info['abi'])

    other_w3 = w3_dest if chain == 'source' else w3_source
    other_contract = other_w3.eth.contract(address=Web3.to_checksum_address(other_info['address']), abi=other_info['abi'])

    # Set up signing account
    warden = Account.from_key(info["signing_key"])

    latest_block = w3.eth.block_number
    from_block = max(latest_block - 5, 0)
    to_block = latest_block

    # Event name and action depending on source or destination
    if chain == "source":
        event_name = "Deposit"
        target_function = "wrap"
        w3_target = w3_dest
        target_contract = other_contract
    else:
        event_name = "Unwrap"
        target_function = "withdraw"
        w3_target = w3_source
        target_contract = other_contract

    # Get event signature hash
    event_abi = [abi for abi in contract.abi if abi['type'] == 'event' and abi['name'] == event_name][0]
    event_signature_hash = w3.keccak(text=f"{event_abi['name']}({','.join([input['type'] for input in event_abi['inputs']])})").hex()

    logs = w3.eth.get_logs({
        "fromBlock": from_block,
        "toBlock": to_block,
        "address": Web3.to_checksum_address(info['address']),
        "topics": [event_signature_hash]
    })

    for log in logs:
        event = contract.events[event_name]().process_log(log)
        args = event['args']
        print(f"Detected {event_name} event: {args}")

        if chain == "source":
            tx = target_contract.functions.wrap(args['token'], args['recipient'], args['amount']).build_transaction({
                'from': warden.address,
                'nonce': w3_target.eth.get_transaction_count(warden.address),
                'gas': 500000,
                'gasPrice': w3_target.eth.gas_price,
            })
        else:
            tx = target_contract.functions.withdraw(args['token'], args['recipient'], args['amount']).build_transaction({
                'from': warden.address,
                'nonce': w3_target.eth.get_transaction_count(warden.address),
                'gas': 500000,
                'gasPrice': w3_target.eth.gas_price,
            })

        signed_tx = warden.sign_transaction(tx)
        tx_hash = w3_target.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"Sent {target_function} transaction: {tx_hash.hex()}")
