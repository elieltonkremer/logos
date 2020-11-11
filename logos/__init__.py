from logos.context import Container, Parameter, Service, ResourceGroup

container = Container({
    'groups.commands': ResourceGroup(r'^app.command.'),
    'app.command': Service(
        klz="logos.command:DelegateCommand",
        parameters={
            'commands': "%groups.commands%"
        }
    )
})
