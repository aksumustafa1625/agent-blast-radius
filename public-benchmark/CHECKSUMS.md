# Integrity

sha256 of the published corpus and of every case source, so a later version
cannot be quietly substituted and no case can be tuned after the fact without
the hash moving.

Verify, from this directory (public-benchmark/):

    grep -E '^    [0-9a-f]{64}  ' CHECKSUMS.md | sed 's/^ *//' | sha256sum -c

or one file at a time:

    sha256sum corpus.json                        # Linux / macOS
    Get-FileHash corpus.json -Algorithm SHA256   # Windows

Every line below is `<sha256>  <path relative to this directory>` - the exact
format `sha256sum -c` reads, so the one-liner needs no path surgery. A Windows
checkout verifies too: the published .gitattributes pins every text file to LF,
and the seal is over LF bytes.

Corpus:

    b8f08890324039db47ae991b38d822b717c4ffd2b2d75f76fc47c4490de45ee7  corpus.json

Case sources:

    24999fa2511214b28eda56c441ccf0e5bdae11880f47169790c6c1057e15e7c8  cases/async-callout.cls
    7ef7a2e60e3ac60b0f9ff24ad51e67532a725a5ac9c58945b1e251cb5d63c79a  cases/async-none-is-clean.cls
    56374f9703934ea83d2fc601ecb475d0d5501bcf78637f3a4e0b422414b1f163  cases/async-platform-event.cls
    5ab060d048c8a75f18b64810e405179924dcc706c6aa0a937b545405026ec66c  cases/async-queueable.cls
    ede8acc86e94bb6e5113fb195a3244648ee3b07a7d9bc020b02027dd30f89650  cases/field-id-only-is-clean.cls
    87d96b506e4dbc4973cb2856da776f8bec9ee3ecba11f6f538415a6e77fed5d4  cases/field-untagged-escalates.cls
    946517f4dbef566fe22d35c15525d2ea7454ceb67362b93b0f1d8b3e2a690162  cases/field-user-can-see-is-clean.cls
    de42aafa9c082efd0d0cfef11788ede68f1042a83a6fdd4d2b13d2c19155d510  cases/prec-v58-with-sharing-plain.cls
    41111cd583a2d84e961931ae9f175792d83aca0746fc4ab24d29c2df567edd47  cases/prec-v58-without-plain.cls
    bc04dae81e5eb5bd75d07f2a8cc12ee74ce79d8cab15f5797cae56d1c14c618f  cases/prec-v58-without-usermode-clause.cls
    e31d345c5988613c53c94b8acd5d7bcba96cd4ed696fdd54ed7c4be541e74c53  cases/prec-v67-no-declaration.cls
    41111cd583a2d84e961931ae9f175792d83aca0746fc4ab24d29c2df567edd47  cases/prec-v67-without-plain.cls
    41005c92fc8305aacebbd017bb6245f39bf740e0306aaf77aa14cc60d78842eb  cases/prec-v67-without-systemmode-clause.cls
    d1ee155fec259b9d84066c1face4a545b46c3891ab792c497256e01981eec784  cases/publish-v58-bypasses-create.cls
    d1ee155fec259b9d84066c1face4a545b46c3891ab792c497256e01981eec784  cases/publish-v67-enforces-create.cls
    e2b1e7de39832d4af6106f939336f491f448f2fdb8ab35e2a06e07c29dea0524  cases/record-v58-with-sharing.cls
    9d0fec2b5adeb19f03fee8d1d87bed31aeffd53b9f9794d4fb1dfb2902af304b  cases/record-v58-without-plain.cls
    9d0fec2b5adeb19f03fee8d1d87bed31aeffd53b9f9794d4fb1dfb2902af304b  cases/record-v67-without-plain.cls
    0e20827fd5b72395672d4040b4f50ae5f4e514e58126448c8ed142c8b1e137e8  cases/sanitizer-discarded-is-a-bug.cls
    59ea8b0f5967ba0aec5f666fdb013797442235a2351779cbd18662e3a5ebf448  cases/sanitizer-readable-used-caps-severity.cls
    39db0f4941d284e5c283ae433479263729a22140825884d986739c44687c9ef8  cases/sanitizer-wrong-accesstype.cls
    17d2fa93248a42ac6033f45d3c8f47ec5de9a2dc518e5d462333d158156e3eab  cases/sosl-returning-gdpr-v58.cls
    17d2fa93248a42ac6033f45d3c8f47ec5de9a2dc518e5d462333d158156e3eab  cases/sosl-returning-gdpr-v67.cls
    fbec86ddceb9cff396349e68e87f231106fe8ecf09fa5f72278a7562235475cd  cases/unknown-dynamic-soql.cls
    38cade2da4bf75b553b56ba9fbca931f05b31f831d354e39c28bdf7ce9d55cdf  cases/unknown-sosl-without-returning.cls
    7daa9045db3f056b49820a8ba9ece1703eb608e7d102b3c215146b3887ddc3bb  cases/write-as-user-is-clean.cls
    9afc529a0ef9dee53af50e1e712b1d05ea152e6e494c547d0f91743eae85db4f  cases/write-v58-plain-insert.cls
    9afc529a0ef9dee53af50e1e712b1d05ea152e6e494c547d0f91743eae85db4f  cases/write-v67-plain-is-clean.cls
