# Integrity

sha256 of the published corpus, so a later version cannot be quietly substituted
and no case can be tuned after the fact without the hash moving.

    corpus.json  fc274b70f7620537d7624c3764faf28ed5654e13f9bb586c2e4240e7e7f1714d

Verify:

    sha256sum corpus.json                    # Linux / macOS
    Get-FileHash corpus.json -Algorithm SHA256   # Windows

Case sources:

    24999fa2511214b28eda56c441ccf0e5bdae11880f47169790c6c1057e15e7c8  async-callout.cls
    7ef7a2e60e3ac60b0f9ff24ad51e67532a725a5ac9c58945b1e251cb5d63c79a  async-none-is-clean.cls
    56374f9703934ea83d2fc601ecb475d0d5501bcf78637f3a4e0b422414b1f163  async-platform-event.cls
    5ab060d048c8a75f18b64810e405179924dcc706c6aa0a937b545405026ec66c  async-queueable.cls
    854f7dc8875972565f944ce6aef8b6d8132b7f51f134934f0d9da5c2fc9512e2  field-id-only-is-clean.cls
    ebd763853393bfd7953f8eec273c07d43f920a99a14cb909aceeb4a58e5ffd44  field-untagged-escalates-ps502.cls
    b74f57e3c5cc10d6adc04894f9fed1952709f6798991cd6e0fb4089e08f2816a  field-user-can-see-is-clean.cls
    da8f34d261995ed3a56c0ec07d670943c65ea6359798842631f87ab74e72d7f4  prec-v58-without-plain.cls
    11d3a0024b37bb6406d017a435eb702d910df55838ef5b1c92d68c0f48deac2d  prec-v58-without-systemmode-clause.cls
    f7fd412b90decc59607482342134072f0e4017f6e5f0f4ad0dbb02cf497e867c  prec-v58-without-usermode-clause.cls
    fdaaaf37b070c89dffa1ad559b771b00519b4fb2f7b06bf2465089f1a858d930  prec-v58-with-sharing-plain.cls
    10131c65405d8b88780638878a233864acd59a0b686d58d2c264a9120eeef7d9  prec-v67-no-declaration.cls
    da8f34d261995ed3a56c0ec07d670943c65ea6359798842631f87ab74e72d7f4  prec-v67-without-plain.cls
    acbfa08b0368547bc7adb431b5408dc5a84c50d715f5e944687edb9ae61f2f92  publish-v58-bypasses-create.cls
    acbfa08b0368547bc7adb431b5408dc5a84c50d715f5e944687edb9ae61f2f92  publish-v67-enforces-create.cls
    b1be83ddc5bdcdd537d3fe8a16b488cc58c9039051e617e6346be404bd622947  record-v58-without-plain.cls
    5e500f15032a1480044a49229405202a0565b7bbaa03e2eaf6f8d4b21e8e05e3  record-v58-with-sharing.cls
    b1be83ddc5bdcdd537d3fe8a16b488cc58c9039051e617e6346be404bd622947  record-v67-without-plain.cls
    e3758f2d0cd2dc668f26f783d894d01db36f500d8a0e127ebc00ec106c8ededd  sanitizer-discarded-is-a-bug.cls
    d98f05dd262fcd07d16a18779339e88c83b337d5e12e6f68086ae58e2f0418c3  sanitizer-readable-used-caps-severity.cls
    3fd21e97faf35a4b0b66de7a1126a31509d0621a65559814677e6fe7efef407e  sanitizer-wrong-accesstype.cls
    2582073e092cd744d0f75e1001272240e5f99f6dfb34f0c3b2fa746ae80f7232  sosl-returning-gdpr-v58.cls
    2582073e092cd744d0f75e1001272240e5f99f6dfb34f0c3b2fa746ae80f7232  sosl-returning-gdpr-v67.cls
    fbec86ddceb9cff396349e68e87f231106fe8ecf09fa5f72278a7562235475cd  unknown-dynamic-soql.cls
    38cade2da4bf75b553b56ba9fbca931f05b31f831d354e39c28bdf7ce9d55cdf  unknown-sosl-without-returning.cls
    534ee5d3c646bf5adf180d4ea658b80b7f2658acef530e9bc4327d937de7089b  write-as-user-is-clean.cls
    8c2f3566b8563c3001c7f19a97234361c1a6240b3626251b5461070e602f892b  write-v58-plain-insert.cls
    8c2f3566b8563c3001c7f19a97234361c1a6240b3626251b5461070e602f892b  write-v67-plain-is-clean.cls