# Get Started

## Usage

### From Source

1. `git clone`
1. Setup python. 3.11.9 is tested
1. Run `setup.ps1` or `setup.sh`
1. Start process by `run.ps1` or `run.sh`

<!--### Binary

1. Run `MessageSyncer` or `MessageSyncer.exe`
-->
### Docker

1. Download [Compose File](../docker/compose.yml)
1. Run `docker compose -f compose.yml up -d`


## Terminology

This is a table of terms of MessageSyncer to help you understand the meaning of
terms will be used in configuration settings and usage.

| Term             | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Adapter          | Items for MessageSyncer to interact with the external messaging interface. There are two types of Adapter: Getter and Pusher.                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Adapter class    | Developed by adapter developers. There are two types of Adapter class: GetterClass and PusherClass. They are usually named after the message interface, such as `Weibo` or `Onebot11`, which is controlled by the developer.                                                                                                                                                                                                                                                                                                                                                          |
| Adapter instance | An adapter instance is the instantiation result of the Adapter class. <br>An instance can have an id. <br>For MessageSyncer, the id is only used to distinguish it from other instances of the same adapter class; the adapter handles and uses this id by itself. If an instance has an id, it can be referred to in the form of `{Getter class}.{id}`, such as `Weibo.1234567890`; if this instance does not have an id, it can be referred to as `{Getter class}`, such as `Announcement`, in which case its name is the same as its class, and it can be regarded as a singleton. |
| Getter           | The source from which MessageSyncer gets messages, they have triggers that periodically refresh and get the latest message list.                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Pusher            | MessageSyncer can send message via pusher.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Pusher detail    | `{PusherInstanceStr}.{towhere}`, where `towhere` is the destination of the message, and this field is directly passed to Pusher for processing.                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Pair             | `{GetterInstance} {PusherDetail}`, where all dot separators of `PusherDetail` cannot be omitted. Eg. `Weibo.1234567890 Onebot.bot1.user1`                                                                                                                                                                                                                                                                                                                                                                                                                                             |
